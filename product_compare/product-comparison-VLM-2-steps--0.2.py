"""
train.py — Fine-tune Qwen3-VL for product pair matching
Hardware target: Mobile RTX 4090 (16 GB VRAM) + 32 GB system RAM
Dataset: 134 000 training pairs  |  2 000 eval samples (sampled from 33 000)
"""

import os
import math
import random
import logging
import argparse
from pathlib import Path
from typing import Optional

import torch
import pandas as pd
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from transformers import (
    Qwen2_5_VLForConditionalGeneration,   # Qwen3-VL shares this class
    AutoTokenizer,
    AutoProcessor,
    get_cosine_schedule_with_warmup,
)
from peft import LoraConfig, get_peft_model, TaskType
import bitsandbytes as bnb

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Hyper-parameters  (tune via CLI args below)
# ─────────────────────────────────────────────
TRAIN_SIZE        = 134_000
TEST_EVAL_SAMPLE  = 2_000
BATCH_SIZE        = 2          # per-device; gradient accumulation brings effective BS up
GRAD_ACCUM        = 8          # effective batch = 16
MAX_NEW_TOKENS    = 8          # we only need "Yes" / "No"
MAX_SEQ_LEN       = 1024       # input token budget
LEARNING_RATE     = 2e-4
NUM_EPOCHS        = 1          # 134 k samples, 1 epoch ≈ enough for fine-tuning
WARMUP_RATIO      = 0.03
KEEP_CKPTS        = 3          # rolling window of saved checkpoints
SAVE_EVERY_STEPS  = 500        # save / eval every N optimizer steps
SEED              = 42

# LoRA keeps VRAM manageable on 16 GB
LORA_R            = 16
LORA_ALPHA        = 32
LORA_DROPOUT      = 0.05
LORA_TARGET       = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"]

# ─────────────────────────────────────────────
# Step budget math
# ─────────────────────────────────────────────
STEPS_PER_EPOCH   = math.ceil(TRAIN_SIZE / (BATCH_SIZE * GRAD_ACCUM))
TOTAL_STEPS       = STEPS_PER_EPOCH * NUM_EPOCHS
# e.g.  134000 / (2*8) = 8375 optimizer steps per epoch
#       save every 500 steps  → ~16 checkpoints; rolling window keeps last 3


# ─────────────────────────────────────────────
# Chat-template builder
# ─────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a product matching expert. "
    "Given two product listings (title + image), decide whether they refer to "
    "the SAME physical product. "
    "Reply with exactly one word: Yes or No."
)


def build_chat_messages(
    title1: str,
    title2: str,
    image1: Optional[Image.Image],
    image2: Optional[Image.Image],
    label: Optional[int] = None,
) -> list[dict]:
    """
    Returns a list of messages in the Qwen3-VL / Qwen2.5-VL chat format.

    The processor's apply_chat_template will insert the special vision tokens
    (<|vision_start|> … <|vision_end|>) automatically when it sees
    {"type": "image"} content blocks.

    If `label` is given the assistant turn is appended (for training).
    """
    user_content = []

    # ── Product 1 ──
    user_content.append({"type": "text", "text": "**Product 1**"})
    if image1 is not None:
        user_content.append({"type": "image", "image": image1})
    user_content.append({"type": "text", "text": f"Title: {title1}"})

    # ── Product 2 ──
    user_content.append({"type": "text", "text": "\n**Product 2**"})
    if image2 is not None:
        user_content.append({"type": "image", "image": image2})
    user_content.append({"type": "text", "text": f"Title: {title2}"})

    user_content.append({
        "type": "text",
        "text": "\nAre these two listings the same product? Answer Yes or No.",
    })

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    if label is not None:
        answer = "Yes" if label == 1 else "No"
        messages.append({"role": "assistant", "content": answer})

    return messages


# ─────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────
class ProductPairDataset(Dataset):
    """
    Lazy-loading dataset.  Images are opened on __getitem__ so that only
    BATCH_SIZE images live in RAM at a time.

    image1 / image2 columns hold file paths.  If a path is missing / corrupt
    we silently fall back to a None (the chat template skips the image block).
    """

    def __init__(self, csv_path: str, image_root: str = "", is_eval: bool = False,
                 eval_sample: int = TEST_EVAL_SAMPLE, seed: int = SEED):
        df = pd.read_csv(csv_path)

        # Required columns sanity check
        required = {"title1", "title2", "image1", "image2", "Label"}
        assert required.issubset(df.columns), f"CSV missing columns: {required - set(df.columns)}"

        if is_eval and len(df) > eval_sample:
            df = df.sample(n=eval_sample, random_state=seed).reset_index(drop=True)
            logger.info("Eval dataset sampled: %d rows", len(df))

        self.df         = df
        self.image_root = image_root

    def __len__(self) -> int:
        return len(self.df)

    def _load_image(self, path: str) -> Optional[Image.Image]:
        if not path or pd.isna(path):
            return None
        full = os.path.join(self.image_root, path) if self.image_root else path
        try:
            img = Image.open(full).convert("RGB")
            return img
        except Exception:
            return None

    def __getitem__(self, idx: int) -> dict:
        row    = self.df.iloc[idx]
        image1 = self._load_image(str(row["image1"]))
        image2 = self._load_image(str(row["image2"]))
        label  = int(row["Label"])
        return {
            "title1":  str(row["title1"]),
            "title2":  str(row["title2"]),
            "image1":  image1,
            "image2":  image2,
            "label":   label,
        }


# ─────────────────────────────────────────────
# Collator
# ─────────────────────────────────────────────
class ProductPairCollator:
    """
    Converts a list of raw samples into model-ready tensors.

    For training  : appends the assistant answer → used as labels.
    For inference : does NOT append the assistant turn.
    """

    def __init__(self, processor, training: bool = True,
                 max_length: int = MAX_SEQ_LEN):
        self.processor  = processor
        self.training   = training
        self.max_length = max_length

    def __call__(self, batch: list[dict]) -> dict:
        all_messages = []
        all_images   = []
        labels_int   = []

        for sample in batch:
            msgs = build_chat_messages(
                title1=sample["title1"],
                title2=sample["title2"],
                image1=sample["image1"],
                image2=sample["image2"],
                label=sample["label"] if self.training else None,
            )
            all_messages.append(msgs)

            # Collect images in order (processor needs them as a flat list)
            imgs = []
            if sample["image1"] is not None:
                imgs.append(sample["image1"])
            if sample["image2"] is not None:
                imgs.append(sample["image2"])
            all_images.append(imgs if imgs else None)

            labels_int.append(sample["label"])

        # Apply Qwen chat template to get text strings
        texts = [
            self.processor.apply_chat_template(
                msgs,
                tokenize=False,
                add_generation_prompt=not self.training,
            )
            for msgs in all_messages
        ]

        # Flatten images for the processor
        flat_images = []
        for imgs in all_images:
            flat_images.extend(imgs or [])

        # Tokenize + vision encoding
        inputs = self.processor(
            text=texts,
            images=flat_images if flat_images else None,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )

        if self.training:
            # Build label tensor: -100 everywhere except the assistant answer tokens
            input_ids = inputs["input_ids"]         # (B, L)
            labels    = input_ids.clone()

            # Mask everything up to (and including) the last non-padding position
            # of the user/system turns.  We do this by finding the assistant
            # answer token(s) at the tail of each sequence.
            #
            # Qwen3-VL puts <|im_end|> at the end of each role block.
            # The assistant turn we appended is the LAST segment.
            # Strategy: find the second-to-last <|im_end|> and mask up to it.

            im_end_id = self.processor.tokenizer.convert_tokens_to_ids("<|im_end|>")

            for i in range(input_ids.size(0)):
                seq = input_ids[i].tolist()
                # Find all positions of <|im_end|>
                end_positions = [j for j, t in enumerate(seq) if t == im_end_id]
                if len(end_positions) >= 2:
                    # Mask everything up to and including the second-to-last <|im_end|>
                    mask_up_to = end_positions[-2]
                    labels[i, : mask_up_to + 1] = -100
                # Mask padding tokens
                pad_id = self.processor.tokenizer.pad_token_id
                labels[i][input_ids[i] == pad_id] = -100

            inputs["labels"] = labels

        inputs["label_int"] = torch.tensor(labels_int, dtype=torch.long)
        return inputs


# ─────────────────────────────────────────────
# Accuracy helper
# ─────────────────────────────────────────────
def decode_to_binary(token_ids: torch.Tensor, tokenizer) -> list[int]:
    """
    Decode generated token ids and map 'Yes' → 1, 'No' → 0.
    Any other output is mapped to -1 (invalid).
    """
    results = []
    for ids in token_ids:
        text = tokenizer.decode(ids, skip_special_tokens=True).strip().lower()
        if text.startswith("yes"):
            results.append(1)
        elif text.startswith("no"):
            results.append(0)
        else:
            results.append(-1)
    return results


def compute_accuracy(preds: list[int], golds: list[int]) -> float:
    valid = [(p, g) for p, g in zip(preds, golds) if p != -1]
    if not valid:
        return 0.0
    correct = sum(p == g for p, g in valid)
    return correct / len(valid)


# ─────────────────────────────────────────────
# Checkpoint helpers
# ─────────────────────────────────────────────
def save_checkpoint(model, optimizer, scheduler, step: int,
                    output_dir: str, keep: int = KEEP_CKPTS):
    ckpt_dir = Path(output_dir) / f"checkpoint-{step}"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ckpt_dir)
    torch.save({
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "step": step,
    }, ckpt_dir / "trainer_state.pt")
    logger.info("Saved checkpoint: %s", ckpt_dir)

    # Rolling delete: keep only the most recent `keep` checkpoints
    all_ckpts = sorted(
        [d for d in Path(output_dir).iterdir()
         if d.is_dir() and d.name.startswith("checkpoint-")],
        key=lambda d: int(d.name.split("-")[1]),
    )
    for old in all_ckpts[:-keep]:
        import shutil
        shutil.rmtree(old)
        logger.info("Removed old checkpoint: %s", old)


# ─────────────────────────────────────────────
# Evaluation loop (generation-based)
# ─────────────────────────────────────────────
@torch.no_grad()
def evaluate(model, dataloader, tokenizer, device) -> float:
    model.eval()
    all_preds, all_golds = [], []

    for batch in dataloader:
        label_int = batch.pop("label_int").tolist()
        # Remove labels key if present (eval collator won't add it, but guard)
        batch.pop("labels", None)
        batch = {k: v.to(device) for k, v in batch.items() if isinstance(v, torch.Tensor)}

        generated = model.generate(
            **batch,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
        # Slice off the prompt tokens
        prompt_len = batch["input_ids"].shape[1]
        new_tokens = generated[:, prompt_len:]

        preds = decode_to_binary(new_tokens, tokenizer)
        all_preds.extend(preds)
        all_golds.extend(label_int)

    acc = compute_accuracy(all_preds, all_golds)
    model.train()
    return acc


# ─────────────────────────────────────────────
# Training loop
# ─────────────────────────────────────────────
def train(args):
    random.seed(SEED)
    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s", device)

    # ── Model & Processor ──────────────────────
    logger.info("Loading model: %s", args.model_name)
    processor = AutoProcessor.from_pretrained(
        args.model_name, trust_remote_code=True
    )

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        args.model_name,
        torch_dtype=torch.bfloat16,   # bfloat16 halves VRAM vs fp32
        device_map="auto",            # offload layers to CPU/disk if needed
        trust_remote_code=True,
    )

    # ── LoRA ────────────────────────────────────
    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET,
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # ── Datasets & DataLoaders ─────────────────
    train_ds = ProductPairDataset(args.train_csv, image_root=args.image_root)
    eval_ds  = ProductPairDataset(args.test_csv,  image_root=args.image_root,
                                  is_eval=True, eval_sample=TEST_EVAL_SAMPLE)

    train_collator = ProductPairCollator(processor, training=True)
    eval_collator  = ProductPairCollator(processor, training=False)

    train_loader = DataLoader(
        train_ds,
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=train_collator,
        num_workers=4,
        pin_memory=True,
        prefetch_factor=2,
        persistent_workers=True,
    )
    eval_loader = DataLoader(
        eval_ds,
        batch_size=BATCH_SIZE * 2,   # larger BS is fine for inference
        shuffle=False,
        collate_fn=eval_collator,
        num_workers=2,
        pin_memory=True,
    )

    # ── Optimizer & Scheduler ──────────────────
    optimizer = bnb.optim.AdamW8bit(
        [p for p in model.parameters() if p.requires_grad],
        lr=LEARNING_RATE,
        weight_decay=0.01,
    )

    total_steps   = math.ceil(len(train_loader) / GRAD_ACCUM) * NUM_EPOCHS
    warmup_steps  = max(1, int(total_steps * WARMUP_RATIO))
    scheduler     = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    logger.info("Total optimizer steps: %d  |  Warmup: %d  |  Save every: %d",
                total_steps, warmup_steps, SAVE_EVERY_STEPS)

    # ── Training ────────────────────────────────
    model.train()
    optimizer.zero_grad()
    global_step   = 0
    accum_counter = 0
    running_loss  = 0.0

    for epoch in range(NUM_EPOCHS):
        logger.info("── Epoch %d / %d ──", epoch + 1, NUM_EPOCHS)

        for batch_idx, batch in enumerate(train_loader):
            label_int = batch.pop("label_int")   # not needed for loss
            batch = {k: v.to(device) for k, v in batch.items()
                     if isinstance(v, torch.Tensor)}

            outputs = model(**batch)
            loss    = outputs.loss / GRAD_ACCUM
            loss.backward()
            running_loss += loss.item()
            accum_counter += 1

            if accum_counter == GRAD_ACCUM:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                accum_counter = 0
                global_step  += 1

                if global_step % 50 == 0:
                    logger.info(
                        "Step %5d | loss=%.4f | lr=%.2e",
                        global_step,
                        running_loss / 50,
                        scheduler.get_last_lr()[0],
                    )
                    running_loss = 0.0

                # ── Save & Eval ──────────────────
                if global_step % SAVE_EVERY_STEPS == 0:
                    acc = evaluate(model, eval_loader,
                                   processor.tokenizer, device)
                    logger.info("Step %d | eval accuracy = %.4f", global_step, acc)
                    save_checkpoint(model, optimizer, scheduler,
                                    global_step, args.output_dir)

        logger.info("Epoch %d complete.", epoch + 1)

    # Final save
    save_checkpoint(model, optimizer, scheduler,
                    global_step, args.output_dir)
    logger.info("Training complete.  Final model saved at step %d.", global_step)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Qwen3-VL product comparison trainer")
    p.add_argument("--model_name",  default="Qwen/Qwen2.5-VL-7B-Instruct",
                   help="HF model id or local path")
    p.add_argument("--train_csv",   required=True)
    p.add_argument("--test_csv",    required=True)
    p.add_argument("--image_root",  default="",
                   help="Root dir prepended to image paths in the CSV")
    p.add_argument("--output_dir",  default="./output")
    return p.parse_args()


if __name__ == "__main__":
    train(parse_args())