Given the constraint that **the base LLM architecture cannot be modified**, the evolutionary system should operate on the **training and inference control surface** around the model. In practice, this surface is still very large. Most state-of-the-art improvements in applied LLM systems come from manipulating these surrounding elements rather than changing the transformer itself.

Below is a structured view of **what the OpenEvolve-style engine can mutate and optimize** when working with fixed open-source LLMs.

---

# Evolvable Control Surface for Pretrained LLM Systems

The system evolves **training strategies, inference policies, and data interfaces** rather than the model architecture.

We can divide the search space into six categories.

---

# 1. Data Sampling & Curriculum Strategy

Data scheduling is one of the **highest leverage optimization points**.

Evolution can discover how training data should be sampled over time.

## Evolvable Parameters

### Dataset mixture weights

Adjust proportions of different datasets.

Example

```
dataset_mix = {
  product_catalog: 0.35
  customer_chat: 0.25
  competitor_products: 0.20
  synthetic_training: 0.20
}
```

Evolution mutates these weights.

---

### Difficulty curriculum

Training may start with simpler examples and move toward harder ones.

Possible dimensions:

* product description length
* ambiguity level
* number of attributes
* noise level

Evolution searches schedules such as:

```
epoch 1-3   : easy samples
epoch 4-6   : medium
epoch 7-10  : adversarial samples
```

---

### Hard example mining

Examples mispredicted during evaluation can be replayed more often.

Mutation parameters:

```
hard_sample_ratio
replay_window
difficulty_threshold
```

---

# 2. Loss Function Design

Loss functions dramatically impact model behavior.

An evolutionary system can discover **hybrid losses**.

## Candidate Loss Families

### Cross entropy variants

```
L = CrossEntropy
```

Mutations:

* label smoothing
* temperature scaling
* class weighting

---

### Margin ranking losses

Important for tasks like product matching or fraud detection.

Example

```
L = max(0, margin - score_pos + score_neg)
```

Evolution can mutate:

```
margin ∈ [0.1, 2.0]
negative_sampling_strategy
```

---

### Multi-objective loss

For eCommerce tasks we often care about multiple metrics:

Example:

```
L = w1 * CE
  + w2 * RankingLoss
  + w3 * CalibrationLoss
```

Evolution mutates:

```
w1, w2, w3
```

---

### KL regularization

Useful when distilling from a stronger model.

```
L = CE + λ * KL(student || teacher)
```

Evolution searches λ.

---

# 3. Negative Sampling Strategy

Negative sampling is crucial for:

* product matching
* search ranking
* fraud detection

Evolution can control:

### Hard negative mining

```
top-k nearest neighbors
same category negatives
price-close negatives
```

### Cross-batch negatives

Reuse negatives from other samples.

### Adversarial negatives

Generate synthetic confusing examples.

Example:

```
iPhone 15 case
iPhone 15 Pro case
```

These are highly informative negatives.

---

# 4. Inference-Time Policies

Even if the model is fixed, inference behavior can change drastically.

Evolution can search optimal inference policies.

## Decoding parameters

Mutatable variables:

```
temperature
top_p
top_k
repetition_penalty
beam_size
```

---

## Dynamic decoding

Inference policy may depend on input.

Example:

```
if question_complexity > threshold:
    use beam_search
else:
    greedy_decode
```

Evolution can learn these policies.

---

# 5. Prompt and Context Optimization

For instruction-tuned LLMs this is a **huge search space**.

Evolution can modify:

### Prompt templates

Example mutation:

```
Task: Determine if two products are identical.

vs

You are a retail expert verifying if two product listings represent the same SKU.
```

---

### Few-shot example selection

Parameters:

```
number_of_examples
example_selection_strategy
```

Strategies:

* semantic similarity
* diversity sampling
* adversarial examples

---

### Chain-of-thought policies

Possible mutations:

```
cot_length
cot_trigger_phrases
self_consistency_runs
```

---

# 6. Fine-Tuning Strategy

Even when the base architecture is frozen, we can optimize the **fine-tuning process**.

Evolution can adjust:

---

## LoRA parameters

If using LoRA adapters:

```
rank
alpha
dropout
target_layers
```

---

## Learning rate schedule

Mutation space:

```
lr_initial
warmup_steps
decay_schedule
cosine vs linear
```

---

## Batch construction

Parameters:

```
batch_size
sequence_packing_strategy
gradient_accumulation_steps
```

---

## Regularization

Mutations:

```
dropout_rate
weight_decay
gradient_clipping
```

---

# 7. Evaluation Aggregation

Evolution may also modify **how outputs are aggregated**.

Example:

### Self-consistency

Run the model multiple times:

```
answer = majority_vote(samples)
```

Evolution mutates:

```
num_samples
aggregation_method
```

---

### Hybrid pipelines

Example:

```
LLM prediction
   ↓
rule validation
   ↓
fallback LLM
```

Evolution may discover optimal orchestration.

---

# 8. Data Augmentation

Another high-leverage surface.

Evolution can create transformations such as:

* attribute shuffling
* synonym replacement
* synthetic variants
* noise injection
* product title perturbation

These increase robustness.

---

# 9. System-Level Pipeline Evolution

The system may evolve **multi-stage pipelines** rather than single models.

Example pipeline for product matching:

```
embedding retrieval
        ↓
LLM verification
        ↓
rule validator
```

Evolution can modify:

* thresholds
* stage order
* gating policies.

---

# 10. What the Evolution Engine Actually Mutates

In practice, a candidate solution might look like:

```
{
  dataset_mix
  curriculum_schedule
  loss_structure
  negative_sampling_strategy
  lora_config
  lr_schedule
  decoding_policy
  prompt_template
}
```

This configuration is mutated, trained, and evaluated.

---

# Why This Works Despite Fixed Model Architecture

Even with a frozen architecture, these control surfaces determine:

* representation learning
* decision boundaries
* reasoning reliability
* generalization

Many real-world model improvements come from these dimensions rather than architecture.

Examples from industry:

* OpenAI RLHF tuning
* Google data curriculum tuning
* DeepMind AlphaCode sampling strategies

All achieved major gains without changing the core transformer.

---

# Recommended Evolution Search Priorities

For eCommerce tasks, prioritize mutation in this order:

### Highest Impact

1. Data sampling
2. hard negative mining
3. loss function design

---

### Medium Impact

4. prompt templates
5. LoRA configuration
6. curriculum scheduling

---

### Lower Impact

7. decoding parameters
8. batch construction

---

# Key Insight

You are not evolving a **model architecture**.

You are evolving a **training program**.

Conceptually:

```
Model = fixed
TrainingProgram = evolvable
```

The evolutionary system searches for the **optimal training program**.

---

If you'd like, I can also show the **exact OpenEvolve-style genome representation** for this system (how the training program becomes a mutatable “DNA” structure), which is the critical step to making this actually work in practice.
