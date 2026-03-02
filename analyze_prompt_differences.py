import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib

# Use non-interactive backend
matplotlib.use("Agg")

# Configuration
INPUT_CSV = "social_proof_results_v3.csv"
OUTPUT_FILE = "super_graph_by_image_v3.png"

# 🚨 AUTO-MAPPING: Matches your specific screenshots to Categories
IMAGE_CATEGORIES = {
"10.18.38": "Activity Message (High Demand)",
    "10.26.13": "Activity Message (View Count)",
    
    "10.19.02": "Fake Reviews (Star Rating)",
    "10.19.12": "Fake Reviews (Star Rating)",
    "10.27.03": "Testimonial Popup",
    "10.27.15": "Testimonial Popup",
    
    "10.26.24": "Authority Badge (Expert)",
    
    "10.21.06": "Urgency Popup (Timer/Fire)",
    
    "10.18.50": "Misdirection (Hidden Ad)",
    
    "10.20.53": "Control (Clean)",
    "10.26.42": "Control (Clean Catalog)",
}

def generate_super_graph():
    print(f"📂 Loading data from {INPUT_CSV}...")
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ Error: Could not find {INPUT_CSV}. Run main.py first.")
        return

    # 1. Clean Data & Scores
    df["Raw Score"] = pd.to_numeric(df["Raw Score"], errors='coerce')
    df = df.dropna(subset=["Raw Score"])
    
    # 2. Add Categories
    def get_category(filename):
        for key, category in IMAGE_CATEGORIES.items():
            if key in filename:
                return category
        return "Uncategorized"
    df["Category"] = df["Image"].apply(get_category)

    # 3. Clean Model Names (Remove 'openai/', 'anthropic/' for space)
    df["Model Short"] = df["Model"].apply(lambda x: x.split('/')[-1])
    
    # 4. Clean Prompt Names
    df["Condition"] = df["Condition"].replace({
        "AVERAGE_CONSUMER": "Average Consumer",
        "CONSUMER_ADVOCATE": "Consumer Advocate"
    })

    # Sort data so the charts appear in a logical order (Category -> Image)
    df = df.sort_values(by=["Category", "Image", "Model Short"])

    # =========================================================================
    # GENERATE SUPER PLOT
    # =========================================================================
    print("🎨 Generating Super Graph (One Chart Per Image)...")
    
    # Setup styling
    sns.set_theme(style="whitegrid", font_scale=1.1)
    
    # Create FacetGrid: One subplot per Image
    # col_wrap=2 means 2 charts per row (Good balance for detail)
    g = sns.catplot(
        data=df,
        kind="bar",
        x="Model Short",
        y="Raw Score",
        hue="Condition",
        col="Image",
        col_wrap=2,
        height=5, 
        aspect=2.5,  # Make charts wide to fit model names
        palette={"Average Consumer": "#e74c3c", "Consumer Advocate": "#2ecc71"},
        edgecolor="black",
        sharex=False  # Allow x-axis to be independent if needed
    )

    # Customizing Titles and Axis
    for ax, title in zip(g.axes.flat, g.col_names):
        # Get Category for this image
        cat = df[df["Image"] == title]["Category"].iloc[0]
        
        # Set a nice title: "Category: Image Name"
        ax.set_title(f"[{cat}] {title}", fontweight='bold', fontsize=14, pad=15)
        
        # Add a line for "Neutral" score (3.0)
        ax.axhline(3.0, color="gray", linestyle="--", linewidth=1, alpha=0.7)
        
        # Improve X-axis label rotation
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=10)
        ax.set_ylim(0, 5.5)
        ax.set_ylabel("Score (1-5)", fontsize=12)
        ax.set_xlabel("")

    # Add Overall Title
    g.figure.suptitle("Detailed Breakdown: Naive vs. Critical Scores for Each Image", fontsize=20, weight='bold', y=1.02)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save
    plt.savefig(OUTPUT_FILE, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Saved super-sized graph to: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_super_graph()