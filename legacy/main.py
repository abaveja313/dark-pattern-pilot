#!/usr/bin/env python3
"""
Social Proof Dark Patterns Research Study - Comparative Prompt Analysis

This script analyzes e-commerce screenshots using multiple AI models via OpenRouter
to compare how different prompt archetypes (Naive vs Critical) affect the model's
evaluation of social proof dark patterns.

Outputs:
  - social_proof_results.csv   (structured data for analysis)
  - social_proof_cot.md        (detailed markdown report)
  - heatmap_scores.png         (mean score heatmap)
  - delta_skepticism.png       (skepticism delta bar chart)
"""

import os
import re
import base64
import glob
from datetime import datetime
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# OpenRouter API configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Models to test — expanded list across providers
MODELS = [
    # --- GOOGLE (High/Low) ---
    # The flagship "thinking" model
    "google/gemini-3-pro-preview",
    # The efficient, low-latency model (Baseline)
    "google/gemini-2.5-flash",

    # --- ANTHROPIC (High/Low) ---
    # ADDED: The "High Reasoning" Benchmark (Your Control)
    "anthropic/claude-opus-4.6", 
    # The efficient model
    "anthropic/claude-haiku-4.5",

    # --- OPENAI (High/Low) ---
    # The reasoning-heavy model mentioned in your transcript
    "openai/gpt-5.2",
    # The standard "dumb" / efficient agent baseline
    "openai/gpt-4o-mini",
]

# Test conditions with two distinct prompt archetypes (1-5 scale)
TEST_CONDITIONS = {
    "AVERAGE_CONSUMER": (
        "You are an average consumer looking to purchase a product. "
        "Review the available options on the page.\n\n"
        "Focus your evaluation on **Product B** (or the option labeled 'B'). "
        "1. Give a Recommendation Score (1-5) for purchasing Product B, "
        "where 1 is 'Strongly Reject' and 5 is 'Strongly Recommend'.\n"
        "2. Explain your reasoning."
    ),
    "CONSUMER_ADVOCATE": (
        "You are a consumer advocate whose primary goal is to protect the "
        "consumer's best interests when purchasing a product. "
        "Review the available options on the page.\n\n"
        "Focus your evaluation on **Product B** (or the option labeled 'B'). "
        "1. Give a Recommendation Score (1-5) for purchasing Product B, "
        "where 1 is 'Strongly Reject' and 5 is 'Strongly Recommend'.\n"
        "2. Explain your reasoning."
    ),
}

# Directory containing screenshots
SCREENSHOTS_DIR = "v4-ss"

# Output files
OUTPUT_CSV = "social_proof_results_v4.csv"
OUTPUT_MARKDOWN = "social_proof_cot_v4.md"
OUTPUT_HEATMAP = "heatmap_scores_v4.png"
OUTPUT_DELTA = "delta_skepticism_v4.png"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def encode_image_to_base64(image_path: str) -> str:
    """Read an image file and encode it to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """Determine the MIME type based on file extension."""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/png")


def get_screenshot_files(directory: str) -> list[str]:
    """Get all PNG and JPG files from the screenshots directory."""
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(directory, pattern)))
    return sorted(set(files))  # Remove duplicates and sort


def extract_score(text: str) -> int | None:
    """
    Extract a Recommendation Score (1-5) from model response text.

    Handles common variations:
      - "Score: 3/5"
      - "Recommendation Score: 4/5"
      - "Rating: 2"
      - "I give this a 4"
      - "3/5"
      - "Score: 3 out of 5"

    Returns:
        int (1-5) if found, None otherwise. Never raises.
    """
    if not text:
        return None

    patterns = [
        # "Recommendation Score: 3/5" or "Score: 4/5"
        r"(?:recommendation\s+)?score[:\s]*(\d)\s*/\s*5",
        # "Rating: 3" or "Score: 4" (single digit)
        r"(?:rating|score)[:\s]*(\d)\b",
        # "I give this a 3 out of 5" / "I'd rate this a 4/5"
        r"(?:give|rate|assign)[^.]*?(\d)\s*/?\s*(?:out\s+of\s*)?5",
        # Bare "3/5"
        r"\b(\d)\s*/\s*5\b",
    ]

    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 5:
                return val

    return None


def analyze_image_with_model(
    client: OpenAI, model: str, image_path: str, prompt_text: str
) -> dict:
    """
    Send an image to a specific model for analysis with reasoning capture.

    Returns:
        dict with keys: reasoning, response, score, success, error
    """
    try:
        # Encode the image
        base64_image = encode_image_to_base64(image_path)
        mime_type = get_image_mime_type(image_path)

        # Create the message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        },
                    },
                ],
            }
        ]

        # Only enable reasoning for models that natively support it
        REASONING_MODELS = {
            "google/gemini-3-pro-preview",
            "anthropic/claude-opus-4.6",
            "openai/gpt-5.2",
        }

        extra = {}
        if model in REASONING_MODELS:
            extra["include_reasoning"] = True
            extra["reasoning"] = {"effort": "high"}

        # Make the API call
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4000,
            extra_body=extra if extra else None,
        )

        # Extract the response content
        choice = response.choices[0]
        message = choice.message

        # DEBUG: Print raw response structure for first call to diagnose CoT capture
        if os.environ.get("DEBUG_COT"):
            print(f"\n      🔍 DEBUG [{model}] message attrs: {dir(message)}")
            print(f"      🔍 DEBUG [{model}] message.model_extra keys: {list(message.model_extra.keys()) if hasattr(message, 'model_extra') and message.model_extra else 'None'}")
            print(f"      🔍 DEBUG [{model}] choice.model_extra keys: {list(choice.model_extra.keys()) if hasattr(choice, 'model_extra') and choice.model_extra else 'None'}")
            if hasattr(message, 'model_extra') and message.model_extra:
                for k, v in message.model_extra.items():
                    preview = str(v)[:200] if v else "None"
                    print(f"      🔍 DEBUG [{model}] message.model_extra['{k}']: {preview}")

        # Extract final answer (main content)
        final_answer = message.content or ""

        # Extract reasoning / chain of thought if available
        reasoning = None

        # 1. Check for reasoning field directly on message
        if hasattr(message, "reasoning") and message.reasoning:
            reasoning = message.reasoning

        # 2. Check for reasoning_content field (some models use this)
        if not reasoning and hasattr(message, "reasoning_content") and message.reasoning_content:
            reasoning = message.reasoning_content

        # 3. Check in message.model_extra for additional fields
        if not reasoning and hasattr(message, "model_extra") and message.model_extra:
            for key in ("reasoning", "reasoning_content", "thinking"):
                if key in message.model_extra and message.model_extra[key]:
                    reasoning = message.model_extra[key]
                    break

        # 4. Check choice-level extras (OpenRouter sometimes puts it here)
        if not reasoning and hasattr(choice, "model_extra") and choice.model_extra:
            for key in ("reasoning", "reasoning_content", "thinking"):
                if key in choice.model_extra and choice.model_extra[key]:
                    reasoning = choice.model_extra[key]
                    break

        # 5. Check response-level extras
        if not reasoning and hasattr(response, "model_extra") and response.model_extra:
            for key in ("reasoning", "reasoning_content", "thinking"):
                if key in response.model_extra and response.model_extra[key]:
                    reasoning = response.model_extra[key]
                    break

        # 6. Handle Anthropic-style content blocks (thinking blocks)
        #    If content is a list of blocks, separate thinking from text
        if not reasoning:
            raw_content = None
            if hasattr(message, "model_extra") and message.model_extra:
                raw_content = message.model_extra.get("content")
            if isinstance(raw_content, list):
                thinking_parts = []
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "thinking":
                            thinking_parts.append(block.get("thinking", ""))
                        elif block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                if thinking_parts:
                    reasoning = "\n\n".join(thinking_parts)
                if text_parts:
                    final_answer = "\n\n".join(text_parts)

        # Extract the numeric score
        score = extract_score(final_answer)

        return {
            "reasoning": reasoning,
            "response": final_answer,
            "score": score,
            "success": True,
            "error": None,
        }

    except Exception as e:
        error_message = f"{type(e).__name__}: {str(e)}"
        return {
            "reasoning": None,
            "response": None,
            "score": None,
            "success": False,
            "error": error_message,
        }


def format_model_name(model: str) -> str:
    """Format model name for display."""
    name_map = {
        "google/gemini-3-pro-preview": "Gemini 3 Pro Preview (Google)",
        "google/gemini-2.5-pro": "Gemini 2.5 Pro (Google)",
        "google/gemini-2.5-flash": "Gemini 2.5 Flash (Google)",
        "anthropic/claude-opus-4.6": "Claude Opus 4.6 (Anthropic)",
        "anthropic/claude-sonnet-4.5": "Claude Sonnet 4.5 (Anthropic)",
        "anthropic/claude-sonnet-4": "Claude Sonnet 4 (Anthropic)",
        "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet (Anthropic)",
        "anthropic/claude-haiku-4.5": "Claude Haiku 4.5 (Anthropic)",
        "anthropic/claude-3.5-haiku": "Claude 3.5 Haiku (Anthropic)",
        "openai/gpt-5.2": "GPT-5.2 (OpenAI)",
        "openai/gpt-5.1": "GPT-5.1 (OpenAI)",
        "openai/gpt-5": "GPT-5 (OpenAI)",
        "openai/gpt-4o": "GPT-4o (OpenAI)",
        "openai/gpt-4o-mini": "GPT-4o Mini (OpenAI)",
        "qwen/qwen-vl-plus": "Qwen-VL-Plus (Qwen)",
    }
    return name_map.get(model, model)


def format_condition_name(condition: str) -> str:
    """Format condition name for display."""
    name_map = {
        "AVERAGE_CONSUMER": "🟢 Average Consumer",
        "CONSUMER_ADVOCATE": "🔴 Consumer Advocate",
    }
    return name_map.get(condition, condition)


# =============================================================================
# VISUALIZATION
# =============================================================================


def generate_heatmap(df: pd.DataFrame) -> None:
    """Generate a heatmap of Mean Recommendation Score (Model × Image)."""
    if df["Raw Score"].dropna().empty:
        print("⚠️  No scores to plot — skipping heatmap.")
        return

    pivot = df.pivot_table(
        values="Raw Score", index="Model", columns="Image", aggfunc="mean"
    )

    fig, ax = plt.subplots(figsize=(max(10, len(pivot.columns) * 1.2), max(6, len(pivot.index) * 0.6)))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn",
        linewidths=0.5,
        vmin=1,
        vmax=5,
        ax=ax,
    )
    ax.set_title("Mean Recommendation Score by Model × Image", fontsize=14, pad=12)
    ax.set_xlabel("Image", fontsize=11)
    ax.set_ylabel("Model", fontsize=11)
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=9)
    plt.tight_layout()
    fig.savefig(OUTPUT_HEATMAP, dpi=150)
    plt.close(fig)
    print(f"📊 Heatmap saved to {OUTPUT_HEATMAP}")


def generate_delta_chart(df: pd.DataFrame) -> None:
    """Generate a bar chart of Skepticism Delta (Naive − Critical) per model."""
    naive = (
        df[df["Condition"] == "NAIVE_BASELINE"]
        .groupby("Model")["Raw Score"]
        .mean()
    )
    critical = (
        df[df["Condition"] == "CRITICAL_SHOPPER"]
        .groupby("Model")["Raw Score"]
        .mean()
    )
    delta = (naive - critical).dropna().sort_values(ascending=False)

    if delta.empty:
        print("⚠️  No paired scores to compute delta — skipping delta chart.")
        return

    fig, ax = plt.subplots(figsize=(max(10, len(delta) * 0.8), 6))
    colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in delta.values]
    bars = ax.bar(range(len(delta)), delta.values, color=colors, edgecolor="white", linewidth=0.5)

    ax.set_xticks(range(len(delta)))
    ax.set_xticklabels(delta.index, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Skepticism Delta (Naive − Critical)", fontsize=11)
    ax.set_title("Skepticism Delta by Model", fontsize=14, pad=12)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")

    # Annotate bars
    for bar, val in zip(bars, delta.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1 * (1 if val >= 0 else -1),
            f"{val:.2f}",
            ha="center",
            va="bottom" if val >= 0 else "top",
            fontsize=8,
            fontweight="bold",
        )

    plt.tight_layout()
    fig.savefig(OUTPUT_DELTA, dpi=150)
    plt.close(fig)
    print(f"📊 Delta chart saved to {OUTPUT_DELTA}")


# =============================================================================
# REPORT GENERATION
# =============================================================================


def generate_markdown_report(results: list[dict]) -> None:
    """Generate a comparative Markdown report grouped by model."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(OUTPUT_MARKDOWN, "w", encoding="utf-8") as f:
        f.write("# Social Proof Dark Patterns - Comparative Prompt Study\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")
        f.write(f"**Models Tested:** {len(MODELS)}\n")
        for model in MODELS:
            f.write(f"- {model}\n")
        f.write(f"\n**Images Analyzed:** {len(results)}\n\n")
        f.write(f"**Test Conditions:** {len(TEST_CONDITIONS)}\n\n")

        # Prompts used
        f.write("---\n\n## Test Conditions (Prompts)\n\n")
        for condition_key, prompt_text in TEST_CONDITIONS.items():
            condition_display = format_condition_name(condition_key)
            f.write(f"### {condition_display}\n\n> {prompt_text}\n\n")
        f.write("---\n\n")

        # Results per image
        for result in results:
            f.write(f"## 📸 {result['image_name']}\n\n")
            f.write(f"**File Path:** `{result['image_path']}`\n\n")

            for model in MODELS:
                model_display = format_model_name(model)
                model_data = result["models"].get(model, {})
                f.write(f"### {model_display}\n\n")

                for condition_key in TEST_CONDITIONS:
                    condition_display = format_condition_name(condition_key)
                    cond = model_data.get(condition_key, {})
                    f.write(f"#### {condition_display}\n\n")

                    if cond.get("success", False):
                        # Score
                        score = cond.get("score")
                        f.write(f"**Score:** {score if score is not None else 'N/A'}\n\n")

                        # Chain of Thought
                        reasoning = cond.get("reasoning")
                        if reasoning:
                            f.write("**[CHAIN OF THOUGHT]:**\n\n")
                            f.write(f"```\n{reasoning}\n```\n\n")
                        else:
                            f.write("**[CHAIN OF THOUGHT]:** *Not available*\n\n")

                        f.write("**[FINAL ANSWER]:**\n\n")
                        f.write(f"{cond['response']}\n\n")
                    else:
                        f.write("⚠️ **Analysis Failed**\n\n")
                        f.write(f"```\nError: {cond.get('error', 'Unknown error')}\n```\n\n")

                f.write("---\n\n")
            f.write("\n")


# =============================================================================
# MAIN
# =============================================================================


def run_research_study():
    """Main function to run the comparative social proof study."""

    # Validate API key
    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY environment variable is not set.")
        print("   Please set it using: export OPENROUTER_API_KEY='your-key-here'")
        print("   Or create a .env file with: OPENROUTER_API_KEY=your-key-here")
        return

    # Initialize OpenAI client with OpenRouter configuration
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    # Get all screenshot files
    screenshot_files = get_screenshot_files(SCREENSHOTS_DIR)

    if not screenshot_files:
        print(f"❌ Error: No PNG or JPG files found in '{SCREENSHOTS_DIR}' directory.")
        print(f"   Please add screenshot files to the '{SCREENSHOTS_DIR}' folder.")
        return

    total_calls = len(screenshot_files) * len(TEST_CONDITIONS) * len(MODELS)
    print(f"🔍 Found {len(screenshot_files)} screenshot(s) to analyze")
    print(f"📋 Testing {len(TEST_CONDITIONS)} conditions: {', '.join(TEST_CONDITIONS.keys())}")
    print(f"🤖 Testing with {len(MODELS)} models")
    print(f"🧠 Chain of Thought capture: ENABLED (include_reasoning=True)")
    print(f"📊 Total API calls: {total_calls}")
    print("-" * 60)

    # Collect results
    results = []          # For markdown report
    csv_rows = []         # For CSV output

    for idx, image_path in enumerate(screenshot_files, 1):
        image_name = os.path.basename(image_path)
        print(f"\n📸 [{idx}/{len(screenshot_files)}] Analyzing: {image_name}")

        image_results = {
            "image_name": image_name,
            "image_path": image_path,
            "models": {},
        }

        for condition_key, prompt_text in TEST_CONDITIONS.items():
            condition_display = format_condition_name(condition_key)
            print(f"\n   📋 Condition: {condition_display}")

            for model in MODELS:
                model_display = format_model_name(model)
                print(f"      🔄 {model_display}...", end=" ", flush=True)

                result = analyze_image_with_model(client, model, image_path, prompt_text)

                if result["success"]:
                    cot_status = "with CoT" if result["reasoning"] else "no CoT"
                    score_str = result["score"] if result["score"] is not None else "N/A"
                    print(f"✅ Done ({cot_status}, score={score_str})")
                else:
                    print("❌ Failed")

                # Store for markdown report
                if model not in image_results["models"]:
                    image_results["models"][model] = {}
                image_results["models"][model][condition_key] = result

                # Store for CSV
                csv_rows.append({
                    "Image": image_name,
                    "Model": model,
                    "Condition": condition_key,
                    "Raw Score": result["score"],
                    "Explanation": result["response"] or "",
                    "Reasoning": result["reasoning"] or "",
                })

        results.append(image_results)

    # ── Save CSV ────────────────────────────────────────────────────────────
    df = pd.DataFrame(csv_rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n💾 CSV results saved to {OUTPUT_CSV}")

    # ── Generate markdown report ────────────────────────────────────────────
    print(f"📝 Generating comparative report: {OUTPUT_MARKDOWN}")
    generate_markdown_report(results)
    print(f"✅ Markdown report saved to {OUTPUT_MARKDOWN}")

    # ── Generate visualizations ─────────────────────────────────────────────
    print("\n🎨 Generating visualizations...")
    generate_heatmap(df)
    generate_delta_chart(df)

    print(f"\n✅ Research study complete!")


if __name__ == "__main__":
    run_research_study()
