import torch
import pandas as pd
import numpy as np
from datasets import Dataset
from unsloth import FastLanguageModel, is_bf16_supported
from unsloth.chat_templates import get_chat_template
from trl import SFTTrainer, SFTConfig
from transformers import TrainerCallback

# ==========================================
# 1. MODEL & TOKENIZER SETUP (4-Bit)
# ==========================================
print("Loading Model...")
model_name = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit" # Pure text version
max_seq_length = 2048 

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = max_seq_length,
    dtype = None, # Auto-detect
    load_in_4bit = True,
)

# Apply standard Qwen template
tokenizer = get_chat_template(
    tokenizer,
    chat_template = "qwen-2.5",
)

# Setup LoRA
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)

# ==========================================
# 2. BULLETPROOF DATA PROCESSING
# ==========================================
def csv_generator(file_path):
    """
    Reads CSV in chunks to save RAM. 
    Applies the chat template immediately so the Trainer only sees raw text.
    """
    # Chunksize of 1000 is fast for pure text
    df_iter = pd.read_csv(file_path, chunksize=10) 
    
    for df in df_iter:
        # Note: iterrows() is safer for chunks larger than 1 to get all rows
        for _, row in df.iterrows():
            label_text = "Yes" if int(row['Label']) == 1 else "No"
            
            # 1. Build the dictionary (Standard Text Format - NO "type" keys needed)
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
            
            # 2. Convert directly to a formatted string using the tokenizer
            text_string = tokenizer.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=False
            )
            
            # 3. Yield a simple dictionary with the "text" key the Trainer expects
            yield {"text": text_string}

print("Initializing Datasets...")
train_dataset = Dataset.from_generator(csv_generator, gen_kwargs={"file_path": "train_pairs.csv"})
eval_dataset = Dataset.from_generator(csv_generator, gen_kwargs={"file_path": "test_pairs.csv"})

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

def formatting_prompts_func(examples):
    # The SFTTrainer passes batches of data as a dictionary of lists.
    # We just return our pre-formatted 'text' column as a list of strings.
    return examples["text"]
# ==========================================
# 4. TRAINER SETUP & EXECUTION
# ==========================================
print("Setting up Trainer...")
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = train_dataset,
    eval_dataset = eval_dataset,
    formatting_func = formatting_prompts_func,
    dataset_text_field = "text", # No formatting_func needed anymore!
    max_seq_length = max_seq_length,
    dataset_num_proc = 1,
    compute_metrics = compute_metrics,
    args = SFTConfig(
        per_device_train_batch_size = 8,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 100, 
        learning_rate = 2e-4,
        fp16 = not is_bf16_supported(),
        bf16 = is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
        eval_strategy = "steps",
        eval_steps = 20,
        save_strategy = "steps",
        save_steps = 20,
        eval_on_start = True,
    ),
    callbacks = [AccuracyEvalCallback()],
)

torch.cuda.empty_cache() 
print("Starting Training...")
trainer.train()


