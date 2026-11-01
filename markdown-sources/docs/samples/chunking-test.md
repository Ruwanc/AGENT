---
title: Chunking Test Note
tags: [testing, chunking, markdown]
keywords: "rag, embeddings"
created: 2026-10-17
status: draft
rating: 4.5
published: false
author: Ruwan
---

This paragraph sits before the first heading, so its heading path should fall back to the document title. Hash words like issue #42, C# and #include are plain text in Markdown, not tags. An email like name@example.com and a URL like https://example.com/page#section stay as they are.

# Pet Care Handbook

A short introduction to the handbook. It links to [the cats page](cats.md), to [our dog page](dogs.md "Dogs"), and to a heading: [diet section](cats.md#diet). A reference-style link: [Ollama][ollama].

[ollama]: https://ollama.com

## Diet

Cats are obligate carnivores, which means they must eat meat to stay healthy. Dogs are omnivores and can digest a wider range of foods, including some vegetables and grains.

### Treats

Tuna is a popular treat but should be limited to small amounts once or twice a week.

#### Homemade Treats

Bake thin strips of chicken breast at 180°C for 20 minutes. Let them cool completely before serving.

##### Storage

Keep homemade treats in the fridge for up to three days.

###### Freezer Tips

Frozen treats keep for one month. Label the bag with the date.

### Feeding Schedule (small table, should stay whole)

| Age | Meals per day | Portion |
|---|---|---|
| Kitten (0-6 months) | 4 | Small |
| Adult (1-7 years) | 2 | Medium |
| Senior (7+ years) | 2-3 | Small |

### Food Reference (big table, should split between rows and repeat the header)

| Food | Type | Safe for cats | Safe for dogs | Notes |
|---|---|---|---|---|
| Chicken | Meat | Yes | Yes | Cooked, boneless, no seasoning |
| Turkey | Meat | Yes | Yes | Remove skin and fat before serving |
| Salmon | Fish | Yes | Yes | Cooked only; raw salmon can carry parasites |
| Tuna | Fish | Limited | Limited | High mercury; treat only, not a daily food |
| Beef | Meat | Yes | Yes | Lean cuts, cooked, no onions or garlic |
| Eggs | Protein | Yes | Yes | Fully cooked; raw eggs can carry salmonella |
| Rice | Grain | Limited | Yes | Plain white rice can help with upset stomach |
| Carrots | Vegetable | Limited | Yes | Cooked or raw, cut into small pieces |
| Pumpkin | Vegetable | Yes | Yes | Plain canned pumpkin, not pie filling |
| Cheese | Dairy | Limited | Limited | Many adult cats are lactose intolerant |
| Milk | Dairy | No | Limited | Causes diarrhoea in most adult cats |
| Chocolate | Sweet | No | No | Toxic: contains theobromine |
| Grapes | Fruit | No | No | Can cause kidney failure in dogs |
| Onions | Vegetable | No | No | Damages red blood cells |
| Garlic | Vegetable | No | No | More toxic than onions, even in powder form |
| Xylitol | Sweetener | No | No | Found in sugar-free gum; extremely toxic to dogs |
| Blueberries | Fruit | Limited | Yes | Good low-calorie treat for dogs |
| Apples | Fruit | Limited | Yes | Remove seeds and core first |

## Health

Annual vaccines and regular vet visits keep pets healthy.

### Vaccination Checklist (task list)

- [x] Rabies vaccine booked
- [x] Deworming done in September
- [ ] Flea treatment due next month
- [ ] Dental check-up

### Symptoms to Watch (nested lists)

1. Digestive problems
   1. Vomiting more than once a day
   2. Diarrhoea lasting longer than 24 hours
2. Behaviour changes
   - Hiding or not wanting to be touched
   - Sudden aggression
     - Especially when the belly is touched
3. Breathing problems

### A Section That Is Too Small

Ok.

### Empty Section

### Long Paragraph (one paragraph over the size limit, should split on sentences)

Cats spend a large part of their day sleeping, usually between twelve and sixteen hours, and kittens and older cats often sleep even more than that. This behaviour comes from their history as hunters, because hunting takes short bursts of intense energy and the rest of the time is spent conserving it. Most cats are crepuscular, which means they are most active at dawn and at dusk, when their natural prey is also most active. Indoor cats often adapt their sleep to the routine of the people they live with, sleeping while their owners are at work and becoming playful in the evening. A cat that suddenly sleeps much more or much less than usual may be unwell, so changes in sleep are worth noting. Light sleep makes up most of a cat's rest, and during this phase the cat can wake quickly if it hears a noise. Deep sleep happens in shorter periods, and during deep sleep a cat may twitch its whiskers or paws, which some people believe is a sign of dreaming. Providing a warm, quiet and slightly raised sleeping spot helps a cat feel safe. Many cats also like to rotate between several favourite places during the day!

### Long Sentence Without Punctuation (should fall back to a hard cut)

this line deliberately has no full stops or question marks or exclamation marks so the sentence splitter cannot find any boundary and the chunker must fall back to cutting the text at the maximum character limit which is the last resort behaviour described in the chunking module and it keeps going with more words about cats and dogs and feeding times and vet visits and vaccines and treats and toys and blankets and scratching posts and litter boxes and water bowls and grooming brushes and nail clippers and travel carriers and harnesses and leashes and collars and name tags and microchips and insurance papers and adoption records and training notes and walking routes and park visits and holiday plans and pet sitters and neighbours who help out and more words again about cats and dogs and feeding times and vet visits so that this single sentence is clearly longer than eight hundred characters in total

### Long Bullet List (one block over the size limit)

- Brush your cat at least once a week to reduce hairballs and shedding around the house.
- Long-haired breeds such as Persians and Maine Coons may need brushing every day.
- Trim nails every two to three weeks using clippers designed for pets, not human clippers.
- Check ears weekly for dirt, redness or a bad smell, which can be signs of infection.
- Clean teeth with a pet toothpaste; never use human toothpaste because it can be toxic.
- Bathe dogs once a month or when they get dirty, using a gentle dog shampoo.
- Most cats rarely need a bath, because they groom themselves several times a day.
- Wipe around the eyes with a soft damp cloth if you see discharge building up.
- Reward your pet with a treat after grooming so it learns to enjoy the routine.
- Keep grooming sessions short at first and slowly make them longer over time.

## Training

> A quote block: patience and consistency matter more than any single technique.
> Reward the behaviour you want to see, and ignore the behaviour you do not.

> **Tip:** Short training sessions of five to ten minutes work better than one long session.

> **Warning:** Never punish a pet physically; it damages trust and makes behaviour worse.

---

### Commands (definition-style list with bold and italic)

- **Sit**: the first command most dogs learn. *Hold a treat above the nose.*
- **Stay**: build up the distance ***slowly***, one step at a time.
- **Come**: ~~use a stern voice~~ use a happy, inviting voice.
- `Leave it`: useful for keeping dogs away from dropped food.

## Technical Notes

### Python Example (code fence, # lines inside must not become headings)

```python
# This comment starts with "#" but is inside a code fence, so it is NOT a heading
## Neither is this one
import ollama

def embed(text: str) -> list[float]:
    """Return one embedding vector."""
    return ollama.embed(model="bge", input=[text])["embeddings"][0]
```

### Bash Example (tilde fence)

~~~bash
# install dependencies
pip install chromadb ollama python-frontmatter
ollama pull hf.co/CompendiumLabs/bge-base-en-v1.5-gguf
~~~

### Text With Pipes That Is Not a Table

Use the shell pipe like cat notes.txt | grep cats | wc -l to count matching lines, and remember that a | b is not a table row.

### JSON and YAML Snippets

```json
{"note_path": "Pets/Cats.md", "chunk_index": 3, "tags": "pets,cats"}
```

```yaml
collection: vault_chunks
space: cosine
```

### Math (LaTeX)

Cosine similarity is $\cos(\theta) = \frac{A \cdot B}{\|A\| \|B\|}$ and with Chroma's cosine space:

$$
\text{similarity} = 1 - \text{distance}
$$

## Media and Embeds

Image embeds below should be removed by sources.py; the text around them should stay.

![A sleeping cat](images/cat-sleeping.png)
![Dog park](images/dog-park.JPG "Dog park")
<img src="images/tabby.jpeg" width="300" alt="Tabby">

An external image: ![remote](https://example.com/cat.webp) and a link to a PDF that must stay: [vet bill](files/bill.pdf).

## Miscellaneous Formatting

Footnotes are supported in many Markdown flavours[^1]. A comment that should not be visible in preview: <!-- internal note: check vet bill -->.

Inline HTML: <mark>marked text</mark> and <br> a line break.

<details>
<summary>Click to expand</summary>

Hidden details inside an HTML block.

</details>

Unicode and emoji: café, naïve, 日本語, සිංහල, 🐱🐶.

Escaped characters: \# not a heading, \*not italic\*, and 5 \| 6.

[^1]: This is the footnote text.


## Closing Hashes Heading ##

ATX headings may end with closing hashes; they should not appear in the heading path.

Setext Heading Level Two
------------------------

READMEs often use underlined (setext) headings. This one should become "## Setext Heading Level Two".

A horizontal rule after a blank line must stay a rule, not become a heading:

---

# Second Top-Level Heading

A second H1 resets the heading path, so this section's path should be just "Second Top-Level Heading", not nested under Pet Care Handbook.

## Duplicate Heading Name

The first section called Diet was under Pet Care Handbook. This is a different section.

## Diet

A second section with the same heading name "Diet" but under a different parent; its path should be "Second Top-Level Heading > Diet".
