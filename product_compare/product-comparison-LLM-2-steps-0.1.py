
import pandas as pd
import json
from transformers import AutoTokenizer

# Load the official Qwen tokenizer
model_id = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"Loading tokenizer: {model_id}")
tokenizer = AutoTokenizer.from_pretrained(model_id)

def process_csv_to_jsonl(input_csv, output_jsonl):
    print(f"Processing {input_csv} -> {output_jsonl}...")
    
    # Read in chunks to keep memory low
    df_iter = pd.read_csv(input_csv, chunksize=1000)
    
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for df in df_iter:
            for _, row in df.iterrows():
                label_text = "Yes" if int(row['Label']) == 1 else "No"
                
                messages = [
                    {
                        "role": "user",
                        "content": f"Product 1: {row['title1']}\nProduct 2: {row['title2']}\nAre these the same product?"
                    },
                    {
                        "role": "assistant",
                        "content": label_text
                    }
                ]
                
                # Apply template to get raw string
                text_string = tokenizer.apply_chat_template(
                    messages, 
                    tokenize=False, 
                    add_generation_prompt=False
                )
                
                # Write out as a JSON object per line
                json_record = json.dumps({"text": text_string})
                f.write(json_record + '\n')

# Run for both datasets
process_csv_to_jsonl("train_pairs.csv", "train_pairs.jsonl")
process_csv_to_jsonl("test_pairs.csv", "test_pairs.jsonl")
print("Data preparation complete!")

import torch
import numpy as np
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    BitsAndBytesConfig,
    TrainerCallback
)
from peft import (
    LoraConfig, 
    get_peft_model, 
    prepare_model_for_kbit_training
)
from trl import SFTTrainer, SFTConfig

# ==========================================
# 1. NATIVE STREAMING DATASETS
# ==========================================
print("Loading datasets in streaming mode...")
# streaming=True means it reads line-by-line from the hard drive during training.
# CPU RAM usage will stay near zero.
dataset = load_dataset(
    "json", 
    data_files={"train": "train_pairs.jsonl", "eval": "test_pairs.jsonl"}, 
    streaming=True
)

train_dataset = dataset["train"]
eval_dataset = dataset["eval"]

# ==========================================
# 2. MODEL & TOKENIZER (Standard BitsAndBytes)
# ==========================================
print("Loading Model & Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_id)
# Ensure padding token is set for batched training
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

'''
# Configure 4-bit Quantization
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
)
'''
bnb_config = BitsAndBytesConfig(
    load_in_8bit=True,
)


model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto", # Automatically maps to your 4090
)

# Prepare model for standard PEFT training
model = prepare_model_for_kbit_training(model)
model.config.use_cache = False # Required for gradient checkpointing

# Define LoRA Configuration
peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", 
                    "gate_proj", "up_proj", "down_proj"]
)

model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

# ==========================================
# 3. EVALUATION METRICS
# ==========================================
def compute_metrics(eval_preds):
    preds, labels = eval_preds
    preds = preds[:, :-1]
    labels = labels[:, 1:]
    
    mask = labels != -100
    predictions = np.argmax(preds, axis=-1)
    correct = (predictions == labels) & mask
    accuracy = correct.sum() / mask.sum()
    return {"accuracy": accuracy}

class AccuracyEvalCallback(TrainerCallback):
    def on_evaluate(self, args, state, control, metrics, **kwargs):
        if "eval_accuracy" in metrics:
            print(f"\n>>> Step {state.global_step} | Eval Accuracy: {metrics['eval_accuracy']:.4f} <<<\n")


# ==========================================
# 3.1. TIMER FOR TRAINING 
# ==========================================

import time
from transformers import TrainerCallback

class TrainingTimerCallback(TrainerCallback):
    def __init__(self):
        self.step_start_time = None
        self.train_start_time = None

    def on_train_begin(self, args, state, control, **kwargs):
        self.train_start_time = time.time()
        print(f"\n🚀 Training Started at: {time.ctime(self.train_start_time)}")

    def on_step_begin(self, args, state, control, **kwargs):
        self.step_start_time = time.time()

    def on_step_end(self, args, state, control, **kwargs):
        step_duration = time.time() - self.step_start_time
        # 'state.global_step' is the update step (after accumulation)
        # To get the time per actual row: step_duration / gradient_accumulation_steps
        samples_per_step = args.gradient_accumulation_steps * args.per_device_train_batch_size
        
        if state.global_step % args.logging_steps == 0:
            print(f"⏱️  Step {state.global_step} took: {step_duration:.2f}s | "
                  f"Throughput: {samples_per_step / step_duration:.2f} samples/sec")

    def on_train_end(self, args, state, control, **kwargs):
        total_time = time.time() - self.train_start_time
        print(f"\n✅ Training Complete!")
        print(f"Total Duration: {total_time/60:.2f} minutes")


# 3.2 Create a small subset for "during-training" evaluation
eval_dataset_small = dataset["eval"].shuffle(seed=42).take(2000)

# ==========================================
# 4. TRAINER SETUP
# ==========================================
print("Setting up Trainer...")
'''
trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer, 
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    #compute_metrics=compute_metrics,
    args=SFTConfig(
        dataset_text_field="text",   
        max_length = 512,
        per_device_train_batch_size=16,
        #per_device_eval_batch_size=8,
        gradient_accumulation_steps=8,
        #gradient_checkpointing=True,    # MANDATORY: Saves ~4GB+ VRAM
        max_steps=400,
        warmup_steps=5,
        learning_rate=1e-4,
        #fp16=not torch.cuda.is_bf16_supported(),
        #bf16=torch.cuda.is_bf16_supported(),
        bf16=True,
        logging_steps=40,
        optim="paged_adamw_8bit",
        weight_decay=0.01,
        output_dir="outputs",
        eval_strategy="no",
        #eval_steps=25,
        save_strategy="no"
    ),
    callbacks=[TrainingTimerCallback()],
)
'''

SFTargs=SFTConfig(
    dataset_text_field="text",
    max_length=512,
    
    # Training Scale
    max_steps=801,                # Runs exactly 1 full Epoch
    learning_rate=1e-4,           # Slightly lower for a 0.5B model on a longer run
    warmup_steps=5,
    logging_steps=100,
    
    # Checkpoint Strategy (Pick your Step)
    save_strategy="steps",
    save_steps=200,               # Save a model every ~25% of the epoch
    save_total_limit=4,           # Keeps 4 folders on disk (~500MB total for LoRA)
    
    # Evaluation Strategy (Small subset)
    eval_strategy="steps",
    eval_steps=100,               # Evaluate when we save
    per_device_eval_batch_size=8, # 0.5B model can handle batch 4 for eval
    eval_accumulation_steps=1,
    
    # VRAM / Hardware
    gradient_accumulation_steps=8,
    per_device_train_batch_size=16,
    gradient_checkpointing=True,
    optim="paged_adamw_8bit",
    fp16=True,
    output_dir="./qwen_product_checkpoints",
)

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer, 
    train_dataset=train_dataset,
    eval_dataset=eval_dataset_small,
    #compute_metrics=compute_metrics,
    args=SFTargs,
    callbacks=[TrainingTimerCallback()],
)

print("Empty VRAM ...")
torch.cuda.empty_cache()

print(f"Model is on device: {next(model.parameters()).device}")
# Expected output: cuda:0

print("Starting Training...")
trainer.train()


# ===========================================================
# 5.0 Test scoring program against the whole Testing data set
# ===========================================================
from torch.utils.data import DataLoader

print("Empty VRAM ...")
torch.cuda.empty_cache()

# Increase this until you hit ~14GB VRAM
EVAL_BATCH_SIZE = 128 

# Create a loader for your 33k rows
eval_dataloader = DataLoader(dataset["eval"], batch_size=EVAL_BATCH_SIZE)

model.eval()
all_results = []

tokenizer.padding_side = "left" 
tokenizer.pad_token = tokenizer.eos_token # Ensure pad token exists

print(f"Starting Big Eval with Batch Size: {EVAL_BATCH_SIZE}")

for batch in tqdm(eval_dataloader):
    # 'batch' is now a list/dict of 32 samples
    texts = batch["text"] 
    
    # Tokenize the entire batch at once
    inputs = tokenizer(
        texts, 
        return_tensors="pt", 
        padding=True,       # Crucial: adds zeros so all strings in batch are same length
        truncation=True, 
        max_length=512
    ).to("cuda")
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs, 
            max_new_tokens=2,
            pad_token_id=tokenizer.pad_token_id
        )
        
        # Decode the whole batch of results
        batch_responses = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        all_results.extend(batch_responses)


# =====================================================================
# 5.1 formal script to calculate Accuracy using all stored Check Points 
# =====================================================================

import torch
import os
import re
from tqdm import tqdm
from torch.utils.data import DataLoader
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel


print("Empty VRAM ...")
torch.cuda.empty_cache()


# --- 1. CONFIGURATION ---
model_id = "Qwen/Qwen2.5-0.5B-Instruct"
checkpoint_root = "./qwen_product_checkpoints"
EVAL_BATCH_SIZE = 128 
MAX_SEQ_LEN = 512

# --- 2. PREPARE MODEL & TOKENIZER ---
tokenizer = AutoTokenizer.from_pretrained(model_id)
tokenizer.padding_side = "left" 
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

quantization_config = BitsAndBytesConfig(load_in_8bit=True)

base_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quantization_config,
    device_map={"": 0},
    torch_dtype=torch.bfloat16
)

# --- 3. DATASET LOADING ---
# We load the full text. We will split it into Prompt and Ground Truth later.
dataset = load_dataset("json", data_files={"eval": "test_pairs.jsonl"}, streaming=False)
eval_data = dataset["eval"]
eval_dataloader = DataLoader(eval_data, batch_size=EVAL_BATCH_SIZE)

# --- 4. HELPER: EXTRACT PROMPT AND GROUND TRUTH ---
def split_chat_style(text):
    """
    Splits the ChatML string into the prompt (everything up to assistant start)
    and the ground truth (the 'Yes' or 'No' inside the assistant block).
    """
    # Look for the content between <|im_start|>assistant and <|im_end|>
    parts = text.split("<|im_start|>assistant\n")
    if len(parts) < 2:
        return text, "" # Fallback
    
    prompt = parts[0] + "<|im_start|>assistant\n"
    ground_truth = parts[1].replace("<|im_end|>", "").strip().lower()
    return prompt, ground_truth

# --- 5. EVALUATION LOOP ---
checkpoints = [os.path.join(checkpoint_root, d) for d in os.listdir(checkpoint_root) 
               if os.path.isdir(os.path.join(checkpoint_root, d)) and "checkpoint-" in d]
checkpoints.sort()

for ckpt in checkpoints:
    print(f"\n🚀 Evaluating: {ckpt}")
    model = PeftModel.from_pretrained(base_model, ckpt)
    model.eval()
    
    correct_count = 0
    total_count = 0
    
    with torch.no_grad():
        for batch in tqdm(eval_dataloader, desc=f"Processing {os.path.basename(ckpt)}"):
            raw_texts = batch["text"]
            
            prompts = []
            golds = []
            for t in raw_texts:
                p, g = split_chat_style(t)
                prompts.append(p)
                golds.append(g)

            inputs = tokenizer(
                prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=MAX_SEQ_LEN
            ).to("cuda")
            
            outputs = model.generate(
                **inputs,
                max_new_tokens=2, # Only need 'Yes' or 'No'
                pad_token_id=tokenizer.pad_token_id,
                do_sample=False
            )
            
            # Get only the newly generated text
            input_len = inputs.input_ids.shape[1]
            generated_tokens = outputs[:, input_len:]
            predictions = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
            
            for pred, gold in zip(predictions, golds):
                pred_clean = pred.strip().lower()
                
                # Logic: Match if prediction contains the gold label
                if gold in pred_clean:
                    correct_count += 1
                total_count += 1

    # --- 6. RESULTS ---
    accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0
    print(f"\n📊 --- {os.path.basename(ckpt)} STATS ---")
    print(f"✅ Match: {correct_count} / {total_count}")
    print(f"🎯 Accuracy: {accuracy:.2f}%")
    
    model = model.unload()
    torch.cuda.empty_cache()

print("\n✨ Big Eval Complete.")

