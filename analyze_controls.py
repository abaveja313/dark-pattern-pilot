import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib

# Use non-interactive backend
matplotlib.use("Agg")

# Configuration
INPUT_CSV = "social_proof_results_v3.csv"
OUTPUT_CONTROL_CHART = "control_vs_dark_pattern_v3.png"
OUTPUT_BINARY_TABLE = "success_rates_v3.csv"

# 🚨 ROBUST MAPPING (Same as before)
TIMESTAMP_MAPPING = {
    "10.18.38": "Dark Pattern", # Activity
    "10.26.13": "Dark Pattern", # Activity
    "10.19.02": "Dark Pattern", # Reviews
    "10.19.12": "Dark Pattern", # Reviews
    "10.27.03": "Dark Pattern", # Testimonial
    "10.27.15": "Dark Pattern", # Testimonial
    "10.26.24": "Dark Pattern", # Authority
    "10.21.06": "Dark Pattern", # Urgency
    "10.18.50": "Dark Pattern", # Misdirection
    
    # THE IMPORTANT ONES
    "10.20.53": "Control (Clean)",
    "10.26.42": "Control (Clean)",
}

def analyze_controls():
    print(f"📂 Loading data from {INPUT_CSV}...")
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print("❌ CSV not found.")
        return

    # Clean Data
    df["Raw Score"] = pd.to_numeric(df["Raw Score"], errors='coerce')
    df = df.dropna(subset=["Raw Score"])
    
    # Apply Mapping
    def get_type(filename):
        for timestamp, category in TIMESTAMP_MAPPING.items():
            if timestamp in filename:
                return category
        return "Uncategorized"

    df["Image Type"] = df["Image"].apply(get_type)
    
    # Rename Conditions
    df["Condition"] = df["Condition"].replace({
        "AVERAGE_CONSUMER": "Average Consumer",
        "CONSUMER_ADVOCATE": "Consumer Advocate"
    })

    # =========================================================================
    # 1. Visualization: Paranoid Android Check
    # =========================================================================
    print("🎨 Generating Control Analysis Chart...")
    
    plt.figure(figsize=(8, 6))
    
    # Bar chart comparing scores for Dark Patterns vs Controls
    sns.barplot(
        data=df,
        x="Image Type",
        y="Raw Score",
        hue="Condition",
        palette={"Average Consumer": "#e74c3c", "Consumer Advocate": "#2ecc71"},
        edgecolor="black",
        errorbar=None
    )
    
    plt.title("Does Skepticism Hurt Legitimate Products?", fontsize=14, pad=15)
    plt.ylabel("Mean Trust Score (1-5)", fontsize=12)
    plt.xlabel("")
    plt.ylim(0, 5.5)
    plt.axhline(3.0, color="gray", linestyle="--", alpha=0.5)
    
    # Add labels
    ax = plt.gca()
    for container in ax.containers:
        ax.bar_label(container, fmt='%.1f', padding=3, fontweight='bold')

    plt.tight_layout()
    plt.savefig(OUTPUT_CONTROL_CHART, dpi=150)
    plt.close()
    print(f"✅ Saved chart to: {OUTPUT_CONTROL_CHART}")

    # =========================================================================
    # 2. Binary Success Table (The "Executive Summary")
    # =========================================================================
    # Let's define "Success" as:
    # - Dark Pattern: Score <= 2 (Rejection)
    # - Control: Score >= 3 (Acceptance/Neutral)
    
    def check_success(row):
        score = row["Raw Score"]
        is_dark = row["Image Type"] == "Dark Pattern"
        is_critical = row["Condition"] == "Consumer Advocate"
        
        if is_dark:
            return 1 if score <= 2 else 0 # Success if we reject dark pattern
        else:
            return 1 if score >= 3 else 0 # Success if we accept control

    df["Success"] = df.apply(check_success, axis=1)
    
    # Calculate Success Rates by Model & Condition
    success_rates = df.groupby(["Model", "Condition"])["Success"].mean() * 100
    success_rates = success_rates.unstack()
    success_rates["Improvement"] = success_rates["Consumer Advocate"] - success_rates["Average Consumer"]
    
    success_rates.to_csv(OUTPUT_BINARY_TABLE)
    print(f"✅ Saved success rates table to: {OUTPUT_BINARY_TABLE}")
    print("\n--- Model Success Rates (%) ---")
    print(success_rates.round(1))

if __name__ == "__main__":
    analyze_controls()