import os
import json
import random
import math
import pandas as pd
from copy import deepcopy

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

from PIL import Image
from tqdm import tqdm

from transformers import AutoProcessor, AutoModel
from peft import LoraConfig, get_peft_model

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MODEL_NAME = "Qwen/Qwen2-VL-2B-Instruct"  # substitute if needed

MAX_LEN = 128
BATCH_SIZE = 4
STEPS_STAGE1 = 200
STEPS_STAGE2 = 600
POP_SIZE = 8
GENERATIONS = 50


class ProductPairDataset(Dataset):
    def __init__(self, path):

        self.df = pd.read_csv(path)

        # normalize column names (defensive)
        self.df.columns = [c.strip() for c in self.df.columns]

        # fix common typo: "Lael" → label
        if "Label" in self.df.columns:
            self.df["label"] = self.df["Label"]
        elif "label" not in self.df.columns:
            raise ValueError("No label column found")

        # drop rows with missing critical fields
        self.df = self.df.dropna(subset=[
            "title1",
            "title2",
            "image1",
            "image2",
            "label"
        ])

        self.df = self.df.reset_index(drop=True)

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):

        row = self.df.iloc[idx]

        return {
            "text1": str(row["title1"]),
            "text2": str(row["title2"]),
            "image1": str(row["image1"]),
            "image2": str(row["image2"]),
            "label": int(row["label"])
        }
    

#verify
train_path = './train_pairs_cleaned.csv'
eval_path = 'test_pairs.csv'
train_data = ProductPairDataset(train_path)
eval_data = ProductPairDataset(eval_path)

print(train_data.__getitem__(1))

def collate_fn(batch):

    texts1 = [item["text1"] for item in batch]
    texts2 = [item["text2"] for item in batch]

    images1 = []
    images2 = []

    for item in batch:
        try:
            images1.append(Image.open(item["image1"]).convert("RGB"))
            images2.append(Image.open(item["image2"]).convert("RGB"))
        except:
            # fallback: blank image to avoid crash
            images1.append(Image.new("RGB", (224, 224)))
            images2.append(Image.new("RGB", (224, 224)))

    labels = torch.tensor([item["label"] for item in batch]).to(DEVICE)

    return {
        "text1": texts1,
        "text2": texts2,
        "image1": images1,
        "image2": images2,
        "label": labels
    }

class MatchingModel(nn.Module):
    def __init__(self):
        super().__init__()

        self.processor = AutoProcessor.from_pretrained(MODEL_NAME)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.encoder = AutoModel.from_pretrained(
             MODEL_NAME,
             torch_dtype=torch.float16
        ).to(DEVICE)
        
        for p in self.encoder.parameters():
            p.requires_grad = False
        

        lora_config = LoraConfig(
            r=8,
            lora_alpha=16,
            target_modules=["q_proj", "v_proj"]
        )

        self.encoder = get_peft_model(self.encoder, lora_config)

        #hidden = self.encoder.config.hidden_size
        hidden = self.encoder.config.text_config.hidden_size

        self.head = nn.Sequential(
            nn.Linear(hidden * 2, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 2)
        ).to(self.device).to(torch.float16)

        #print(next(self.head.parameters()).device)

    def encode(self, text, image_path):

         if isinstance(image_path, list):
             image_path = image_path[0]
             text = text[0]

         image = Image.open(image_path).convert("RGB")

         messages = [
             {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": f"Product A: {title1}"},
                    {"type": "image"},
                    {"type": "text", "text": f"Product B: {title2}"}
                ]
             }
         ]

         text_input = self.processor.apply_chat_template(
             messages,
             tokenize=False,
             add_generation_prompt=False
         )

         inputs = self.processor(
             text=[text_input],
             images=[image],
             return_tensors="pt",
             padding=True
         ).to(self.device)

         outputs = self.encoder(**inputs)

         hidden_states = outputs.last_hidden_state
         emb = hidden_states[:, -1]  # stable pooling

         return emb
        
    def forward(self, batch):
        emb1 = self.encode(batch["text1"], batch["image1"])
        emb2 = self.encode(batch["text2"], batch["image2"])

        combined = torch.cat([emb1, emb2], dim=-1)
        combined = combined.to(self.device).to(torch.float16)
        #print(combined.device)

        logits = self.head(combined)

        return emb1, emb2, logits
    
class EvoOptimizer:
    def __init__(self, lr=1e-4):
        self.lr = lr
        self.m = {}

    def step(self, param, grad, name):
        if name not in self.m:
            self.m[name] = torch.zeros_like(grad)

        m = self.m[name]

        # ---- EVOLVABLE REGION ----
        m = 0.9 * m + grad
        update = -self.lr * grad / (torch.sqrt(torch.abs(m)) + 1e-6)
        # -------------------------
        

        update = update.to(param.device)
        update = torch.clamp(update, -0.01, 0.01)

        param.data += update
        self.m[name] = m


class EvoLoss:
    def __init__(self, alpha=0.1):
        self.alpha = alpha

    def __call__(self, logits, labels, emb1, emb2):
        ce = F.cross_entropy(logits, labels)

        sim = F.cosine_similarity(emb1, emb2)
        margin = torch.mean(torch.relu(0.5 - sim))

        loss = ce + self.alpha * margin

        return loss
    
class Curriculum:
    def __init__(self):
        pass

    def sample(self, dataset, step):
        if step < 200:
            return random.choice(dataset.data[:len(dataset)//2])
        else:
            return random.choice(dataset.data)
        
def mutate(candidate):

    new = deepcopy(candidate)

    choice = random.choice(["opt", "loss", "curr"])

    if choice == "opt":
        new["opt_lr"] *= random.uniform(0.8, 1.2)

    elif choice == "loss":
        new["alpha"] *= random.uniform(0.5, 1.5)

    elif choice == "curr":
        new["switch_step"] = int(new["switch_step"] * random.uniform(0.8, 1.2))

    return new

def evaluate(model, dataloader):

    model.eval()
    correct = 0
    total = 0

    with torch.no_grad():
        for batch in dataloader:

            _, _, logits = model(batch)

            preds = torch.argmax(logits, dim=-1)
            labels = batch["label"].to(DEVICE)

            correct += (preds == labels).sum().item()
            total += len(labels)

    return correct / total

def train_candidate(candidate, dataset):

    model = MatchingModel()

    optimizer = EvoOptimizer(lr=candidate["opt_lr"])
    loss_fn = EvoLoss(alpha=candidate["alpha"])

    model.train()

    for step in range(STEPS_STAGE1):

        item = dataset[random.randint(0, len(dataset)-1)]

        batch = {
            "text1": [item["text1"]],
            "text2": [item["text2"]],
            "image1": item["image1"],
            "image2": item["image2"],
            "label": torch.tensor([item["label"]]).to(DEVICE)
        }

        emb1, emb2, logits = model(batch)

        loss = loss_fn(logits, batch["label"], emb1, emb2)

        loss.backward()

        for name, p in model.named_parameters():
            if p.grad is not None:
                optimizer.step(p, p.grad, name)

        model.zero_grad()

    return model

def format_genome(genome):
    return {
        "lr": round(genome["opt_lr"], 6),
        "alpha": round(genome["alpha"], 4),
        # extend as needed
    }
    
def run_evolution(train_path, eval_path):

    train_data = ProductPairDataset(train_path)
    eval_data = ProductPairDataset(eval_path)

    eval_loader = DataLoader(eval_data, batch_size=1)

    population = [
        {"opt_lr": 1e-4, "alpha": 0.1, "switch_step": 200}
        for _ in range(POP_SIZE)
    ]

    for gen in range(GENERATIONS):

        results = []

        for cand in population:

            model = train_candidate(cand, train_data)

            acc = evaluate(model, eval_loader)

            cand["fitness"] = acc
            results.append(cand)
            
            print(
                 f"[G{gen}|C{i}] "
                 f"lr={cand['opt_lr']:.5f}, "
                 f"alpha={cand['alpha']:.3f} → "
                 f"{acc:.4f}"
            )

        results.sort(key=lambda x: -x["fitness"])

        print(f"Gen {gen} Best Acc: {results[0]['fitness']}")

        next_pop = results[:POP_SIZE//2]

        while len(next_pop) < POP_SIZE:
            parent = random.choice(next_pop)
            child = mutate(parent)
            next_pop.append(child)

        population = next_pop


run_evolution("train_pairs.csv", "test_pairs.csv")
