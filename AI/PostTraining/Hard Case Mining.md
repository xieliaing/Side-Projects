# Question: 
I have one based on internal business rules. A SKU is the atomic unit to determine if the items are the same or not. We generate a few thousands of positive and negative samples based on the retrieval/ranking approach mentioned above using existing model. For any positive pairs, any other SKU under the same deal would be considered negative pair, and more so a hard negative pair because it would usually the same series of product but varies in color, size, and other attributes. We can also build hard positive pairs based on the human labeled positive pairs where each SKU usually has a couple different title names in internal system but they are the same system.

Your business rule is actually **extremely powerful** and aligns well with how large marketplaces structure training data. Using **SKU as the atomic identity** gives you a reliable way to generate both **hard negatives and hard positives** without relying solely on model predictions.

What you described is essentially a **graph-based training pair expansion strategy**, and it’s widely used in production systems. Let’s formalize it and highlight a few improvements so you can get the most value from it.

---

# 1️⃣ Your Current Logic (Reframed)

You have:

```
SKU = atomic identity
Deal = product family / listing group
```

Example structure:

```
Deal D1
 ├─ SKU1 (Red, 64GB)
 ├─ SKU2 (Blue, 64GB)
 ├─ SKU3 (Black, 128GB)
```

and

```
SKU1 titles
 ├─ title_a
 ├─ title_b
```

This creates two kinds of relationships.

---

# 2️⃣ Hard Negatives From the Same Deal

Rule:

```
different SKU within same deal → negative
```

Example:

```
SKU1: iPhone 13 64GB Red
SKU2: iPhone 13 64GB Blue
```

These are **extremely valuable hard negatives** because:

* brand identical
* model identical
* only attribute differs

These teach the model **fine-grained variant discrimination**.

Your rule:

```
positive pair: (title_a, title_b) of same SKU
hard negative: (SKU1 title, SKU2 title) within same deal
```

This is excellent.

---

# 3️⃣ Hard Positives From SKU Title Variants

For each SKU:

```
SKU1
 ├─ title_a
 ├─ title_b
 ├─ title_c
```

Generate:

```
(title_a, title_b)
(title_a, title_c)
(title_b, title_c)
```

These are **hard positives** because titles may differ significantly.

Example:

```
Apple iPhone 13 128GB Blue
iPhone13 Blue 128GB Apple Smartphone
```

The model learns **semantic equivalence under formatting variation**.

---

# 4️⃣ Graph Expansion (Very Important)

Think of your data as a graph.

Nodes:

```
title
```

Edges:

```
positive → same SKU
negative → different SKU in same deal
```

Example:

```
title_A1 ─ positive ─ title_A2  (same SKU)
title_A1 ─ negative ─ title_B1  (different SKU same deal)
```

Now you can automatically expand training pairs.

This is called **transitive expansion**.

Example:

```
title_A1 = SKU1
title_A2 = SKU1
title_B1 = SKU2
```

You can generate:

```
(A1, A2) positive
(A1, B1) negative
(A2, B1) negative
```

This multiplies training data.

---

# 5️⃣ Pair Explosion Control

Be careful with combinatorics.

If a SKU has 10 titles:

```
10 choose 2 = 45 positive pairs
```

You usually sample:

```
max 5–10 positive pairs per SKU
```

Same for negatives.

---

# 6️⃣ Weight Hard Negatives Higher

Not all negatives are equal.

Recommended weights:

| Pair type           | Weight  |
| ------------------- | ------- |
| Random negative     | 1       |
| Cross-deal negative | 1       |
| Same-deal negative  | **3–5** |

Same-deal negatives teach **variant boundary detection**.

---

# 7️⃣ Combine With Your Retrieval Mining

Your retrieval mining still plays a role.

You will have:

```
model retrieval positives
model retrieval negatives
SKU rule positives
SKU rule negatives
```

Recommended mix:

```
40% SKU positives
20% SKU hard negatives
20% retrieval hard negatives
20% mined hard positives
```

---

# 8️⃣ Add Attribute Swap Negatives

Within a deal, attributes vary.

Example:

```
size
color
capacity
pack count
```

Explicitly highlight these differences.

Example pair:

```
Vitamin C 130mg Bottle 60 Tablets
Vitamin C 130mg Bottle 120 Tablets
```

Negative label.

This improves **attribute sensitivity**.

---

# 9️⃣ One Critical Enhancement (Highly Recommended)

Inside a deal, **not all SKU pairs are equally difficult**.

Example:

```
64GB vs 128GB
```

is easier than

```
Red vs Crimson
```

You can prioritize negatives where:

```
title similarity > threshold
```

Example:

```
cosine(title_embedding) > 0.85
```

These are the **hardest negatives**.

---

# 🔟 Example Pair Generation Code

Simplified Python logic.

```python
from itertools import combinations
import random


def generate_pairs(deals):

    positives = []
    negatives = []

    for deal in deals:

        skus = deal["skus"]

        # positive pairs within SKU
        for sku in skus:
            titles = sku["titles"]

            for a, b in combinations(titles, 2):
                positives.append((a, b))

        # hard negatives across SKU
        for sku_a, sku_b in combinations(skus, 2):

            for ta in sku_a["titles"]:
                for tb in sku_b["titles"]:
                    negatives.append((ta, tb))

    return positives, negatives
```

In practice you would **sample** instead of generating all pairs.

---

# 11️⃣ Why This Strategy Is So Effective

Your business rule guarantees:

```
label correctness ≈ 100%
```

Most ML pipelines struggle with noisy labels.

But SKU identity removes ambiguity.

This allows:

```
very aggressive hard negative mining
```

without label noise.

---

# 12️⃣ Final Training Mix

Recommended dataset composition:

```
30% SKU positive pairs
20% SKU hard negatives (same deal)
20% ANN hard negatives
15% numeric contrastive pairs
10% masked pairs
5% random negatives
```

This creates a **balanced curriculum**.

---

# Key Insight

Your SKU rule essentially gives you a **perfect supervision graph**.

You can use it to generate:

```
millions of high-quality training pairs
```

with **almost zero annotation cost**.

That’s a huge advantage.

---

If you want, I can next show a **very powerful technique used in large catalog matching systems** called:

**“confusion cluster mining.”**

It automatically discovers **groups of products your model repeatedly confuses** and generates thousands of training pairs per cluster. This method often improves models faster than any other mining technique after the first few training iterations.

**Confusion cluster mining** is an advanced hard-example mining method that identifies **groups of products your model consistently confuses with each other**, then generates **large numbers of high-value training pairs** from those groups.

It is extremely effective after a few model iterations because it directly targets **the model’s real decision boundary failures**.

Your **SKU/deal rules + retrieval mining** already give strong supervision. Confusion clusters sit on top of that and focus on **systematic error regions**.

---

# 1️⃣ Core Idea

Instead of mining individual pairs, find **clusters of items that the model believes are very similar**.

Example cluster discovered by the model:

```
Cluster C1
 ├─ SKU_A (Vitamin C milk extract 130mg)
 ├─ SKU_B (Vitamin C milk extract 260mg)
 ├─ SKU_C (Vitamin C milk extract 130mg capsule)
 ├─ SKU_D (Vitamin C milk extract 130mg powder)
```

The model groups them because embeddings are close.

But your SKU rules tell you:

```
A != B
A != C
A != D
```

So the cluster contains **multiple hard negatives**.

---

# 2️⃣ Why Pair Mining Alone Is Not Enough

Traditional mining retrieves:

```
top-K neighbors
```

This gives pairs like:

```
A–B
A–C
A–D
```

But clustering reveals **structure**:

```
A
├─ B
├─ C
└─ D
```

Now you can generate **many more informative pairs**:

```
A–B
A–C
A–D
B–C
B–D
C–D
```

Cluster mining amplifies training signals.

---

# 3️⃣ How Confusion Clusters Are Built

Pipeline:

```
embed catalog
     │
ANN nearest neighbors
     │
similarity graph
     │
graph clustering
     │
confusion clusters
```

Each cluster contains items the model thinks are similar.

---

# 4️⃣ Example Similarity Graph

Edges represent high embedding similarity.

```
SKU_A ── SKU_B
  │        │
  │        │
SKU_C ── SKU_D
```

Graph clustering groups them into a confusion cluster.

---

# 5️⃣ Use SKU Rules To Label Pairs

Inside the cluster:

```
same SKU → positive
different SKU → negative
```

Example:

```
A = SKU1
B = SKU2
C = SKU3
```

Pairs:

```
A-B negative
A-C negative
B-C negative
```

These are **hard negatives** because the model thinks they are similar.

---

# 6️⃣ Hard Positive Mining Inside Clusters

Clusters also reveal **hard positives**.

Example:

```
SKU1 titles
  title_a
  title_b
```

If embeddings place them far apart but they belong to the same SKU:

```
title_a – title_b
```

becomes a **hard positive**.

---

# 7️⃣ Numeric Confusion Clusters

Clusters often reveal numeric confusion automatically.

Example cluster:

```
Vitamin C 130 mg milk extract
Vitamin C 260 mg milk extract
Vitamin C 500 mg milk extract
```

These are **perfect training negatives**.

---

# 8️⃣ Attribute Confusion Clusters

Another common cluster type:

```
iPhone 13 Pro 128GB
iPhone 13 Pro 256GB
iPhone 13 Pro Max 128GB
```

These teach **variant discrimination**.

---

# 9️⃣ Code Example — Building Confusion Clusters

### Step 1: Build similarity graph

```python
import networkx as nx

def build_similarity_graph(neighbors, threshold):

    G = nx.Graph()

    for i, nbrs in enumerate(neighbors):

        for j, sim in nbrs:

            if sim > threshold:
                G.add_edge(i, j)

    return G
```

---

### Step 2: Find clusters

```python
def find_clusters(graph):

    return list(nx.connected_components(graph))
```

---

# 🔟 Generate Training Pairs From Clusters

```python
from itertools import combinations

def generate_pairs(cluster, sku_map):

    positives = []
    negatives = []

    for a, b in combinations(cluster, 2):

        if sku_map[a] == sku_map[b]:
            positives.append((a, b))
        else:
            negatives.append((a, b))

    return positives, negatives
```

---

# 11️⃣ Filtering Large Clusters

Some clusters may become large.

Limit size:

```
max cluster size = 20–50
```

Sample pairs if needed.

---

# 12️⃣ Iterative Confusion Mining

Repeat every model iteration.

Pipeline:

```
train model
     ↓
embed catalog
     ↓
build confusion clusters
     ↓
generate hard pairs
     ↓
retrain
```

Each cycle pushes the model boundary outward.

---

# 13️⃣ Why This Works Extremely Well

Because it focuses training on:

```
regions where the model is uncertain
```

Those regions contain the **highest learning signal**.

Random pairs contain very little information.

---

# 14️⃣ Example Impact in Production Systems

Confusion cluster mining often yields:

```
duplicate recall +15–30%
variant precision +20%
numeric confusion −40%
```

It accelerates model improvement after initial training.

---

# 15️⃣ How It Fits Your Current Pipeline

Your final pipeline could look like this:

```
SKU rules → base positives / negatives
retrieval mining → additional hard pairs
numeric contrastive augmentation
confusion cluster mining
token masking
```

This produces **millions of high-quality training pairs** with minimal manual labeling.

---

✅ **Important insight for your system**

Your **deal → SKU hierarchy** is perfect for confusion clusters because:

```
deal = natural cluster candidate
SKU = ground truth boundary
```

This lets you detect **variant confusion automatically**.

---

If you'd like, I can also show one **very advanced trick specifically for VLM models like Qwen3-VL**:

**multimodal disagreement mining** — where you mine cases where **text similarity and image similarity disagree**, which is one of the strongest signals for training duplicate detectors.

