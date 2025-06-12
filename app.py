import os
import shutil
import streamlit as st
from docx import Document
import re
import json
import pandas as pd

# -----------------------------------------------------------------------------------
# Ensure output directory exists
# -----------------------------------------------------------------------------------
OUTPUT_DIR = "output1"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------------------------------------------------------------
# Utility functions for parsing .docx and extracting transitions
# -----------------------------------------------------------------------------------

def is_header(text: str) -> bool:
    """
    Detects if a paragraph text matches the pattern of a new article header,
    e.g., "62 du 07/05" or similar.
    """
    return bool(re.match(r"^\s*\d+\s+du\s+\d{2}/\d{2}", text))

def extract_articles(doc: Document):
    """
    Given a python-docx Document, iterate through its paragraphs and extract
    tuples of (narrative_text, list_of_transitions).
    """
    paragraphs = [p.text.strip() for p in doc.paragraphs]
    articles = []
    i, N = 0, len(paragraphs)

    while i < N:
        text = paragraphs[i]
        # Marker line
        if text == "À savoir également dans votre département":
            # Collect narrative paragraphs until "Transitions"
            narrative_parts = []
            j = i + 1
            while j < N and not paragraphs[j].startswith("Transitions"):
                if paragraphs[j]:
                    narrative_parts.append(paragraphs[j])
                j += 1
            narrative_text = " ".join(narrative_parts).strip()

            # Collect transitions until next header
            k = j + 1
            transitions = []
            while k < N:
                t = paragraphs[k]
                if not t:
                    k += 1
                    continue
                if is_header(t):
                    break
                transitions.append(t)
                k += 1

            if narrative_text and transitions:
                articles.append((narrative_text, transitions))

            i = k
        else:
            i += 1

    return articles

def split_paragraph_on_transition(narrative: str, transition: str):
    """
    Find the first exact occurrence of `transition` in `narrative`.
    Return (paragraph_a, paragraph_b). If not found, return (None, None).
    """
    idx = narrative.find(transition)
    if idx == -1:
        return None, None
    before = narrative[:idx].strip()
    after = narrative[idx + len(transition):].strip()
    return before, after

# -----------------------------------------------------------------------------------
# Streamlit App
# -----------------------------------------------------------------------------------

st.set_page_config(page_title="Transition Extraction App", layout="centered")
st.title("French News Transition Extractor")

st.markdown("""
Upload a `.docx` file containing regional French news articles.  
This app will:
1. Extract the narrative paragraph after the “À savoir également dans votre département” marker.
2. Detect and split on the listed transitions.
3. Preview the first 10 examples.
4. Save selected outputs into the `output1/` folder.
5. Offer download buttons (individual & ZIP).
""")

# 1. File uploader
uploaded_file = st.file_uploader("Upload a .docx file", type=["docx"])
if not uploaded_file:
    st.info("Please upload a `.docx` file to begin.")
    st.stop()

# 2. Load document
try:
    doc = Document(uploaded_file)
except Exception as e:
    st.error(f"Error reading the .docx file: {e}")
    st.stop()

# 3. Extract articles & transitions
articles = extract_articles(doc)
if not articles:
    st.warning("No structured articles or transitions detected in this document.")
    st.stop()

# 4. Build few-shot examples and counts
fewshot_examples = []
transition_counts = {}
example_counts = {}
all_transitions = []

# Count transitions overall
for narrative, transitions in articles:
    for t in transitions:
        transition_counts[t] = transition_counts.get(t, 0) + 1
        all_transitions.append(t)

# Build up to 3 examples per transition
for narrative, transitions in articles:
    for t in transitions:
        if example_counts.get(t, 0) < 3:
            before, after = split_paragraph_on_transition(narrative, t)
            if before is not None and after is not None:
                fewshot_examples.append({
                    "paragraph_a": before,
                    "transition": t,
                    "paragraph_b": after
                })
                example_counts[t] = example_counts.get(t, 0) + 1

# Prepare other outputs
unique_transitions    = sorted(set(all_transitions))
duplicate_transitions = {t: c for t, c in transition_counts.items() if c > 1}
fewshot_rejected      = {t: c for t, c in transition_counts.items() if c > 3}

# JSONL entries
fewshot_jsonl_entries = []
for ex in fewshot_examples:
    fewshot_jsonl_entries.append({
        "messages": [
            {"role":"system",   "content":"Insert a short, natural transition phrase between two news paragraphs."},
            {"role":"user",     "content":f"Paragraph A: {ex['paragraph_a']}\nParagraph B: {ex['paragraph_b']}"},
            {"role":"assistant","content":ex["transition"]}
        ]
    })

# 5. Preview first 10
st.subheader("Preview of first 10 extracted examples")
df_preview = pd.DataFrame(fewshot_examples[:10])
st.dataframe(df_preview)

st.success(f"Total fewshot examples extracted: {len(fewshot_examples)}")

# 6. Output selection
st.markdown("---")
st.markdown("**Select which files to generate (in `output1/`):**")
gen_json  = st.checkbox("fewshot_examples.json",             True)
gen_jsonl = st.checkbox("fewshot_examples.jsonl",            True)
gen_rej   = st.checkbox("fewshots_rejected.txt",             True)
gen_to    = st.checkbox("transitions_only.txt",              True)
gen_tor   = st.checkbox("transitions_only_rejected.txt",     True)
gen_frej  = st.checkbox("fewshots-fineTuning_rejected.txt",  True)

# 7. Generate & save
if st.button("Generate Files"):
    generated = []

    # a) fewshot_examples.json
    if gen_json:
        path = os.path.join(OUTPUT_DIR, "fewshot_examples.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fewshot_examples, f, ensure_ascii=False, indent=2)
        generated.append("fewshot_examples.json")

    # b) fewshot_examples.jsonl
    if gen_jsonl:
        path = os.path.join(OUTPUT_DIR, "fewshot_examples.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for entry in fewshot_jsonl_entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")
        generated.append("fewshot_examples.jsonl")

    # c) fewshots_rejected.txt
    if gen_rej:
        path = os.path.join(OUTPUT_DIR, "fewshots_rejected.txt")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fewshot_rejected, f, ensure_ascii=False, indent=2)
        generated.append("fewshots_rejected.txt")

    # d) transitions_only.txt
    if gen_to:
        path = os.path.join(OUTPUT_DIR, "transitions_only.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_transitions))
        generated.append("transitions_only.txt")

    # e) transitions_only_rejected.txt
    if gen_tor:
        path = os.path.join(OUTPUT_DIR, "transitions_only_rejected.txt")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(duplicate_transitions, f, ensure_ascii=False, indent=2)
        generated.append("transitions_only_rejected.txt")

    # f) fewshots-fineTuning_rejected.txt
    if gen_frej:
        path = os.path.join(OUTPUT_DIR, "fewshots-fineTuning_rejected.txt")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fewshot_rejected, f, ensure_ascii=False, indent=2)
        generated.append("fewshots-fineTuning_rejected.txt")

    # Notify
    st.success(f"Generated {', '.join(generated)} in `{OUTPUT_DIR}/`")

    # 8. ZIP & download
    zip_path = shutil.make_archive(OUTPUT_DIR, 'zip', OUTPUT_DIR)
    with open(zip_path, 'rb') as fp:
        st.download_button(
            label="📥 Download all outputs as ZIP",
            data=fp,
            file_name=f"{OUTPUT_DIR}.zip",
            mime="application/zip"
        )

    # 9. Individual downloads
    st.markdown("**Download individual files:**")
    for fname in generated:
        file_path = os.path.join(OUTPUT_DIR, fname)
        with open(file_path, 'rb') as f:
            st.download_button(
                label=f"Download {fname}",
                data=f,
                file_name=fname,
                mime="text/plain"
            )
