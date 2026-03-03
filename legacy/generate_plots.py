import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib

# Use non-interactive backend to avoid display errors
matplotlib.use("Agg")

# Configuration
INPUT_CSV = "social_proof_results_v3.csv"
OUTPUT_HEATMAP = "heatmap_scores_v3.png"
OUTPUT_DELTA = "delta_skepticism_v3.png"

def generate_visualizations():
    print(f"📂 Loading data from {INPUT_CSV}...")
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ Error: Could not find {INPUT_CSV}. Make sure it is in the same folder.")
        return

    # Ensure "Raw Score" is numeric (handles strings like "5.0" or "3")
    df["Raw Score"] = pd.to_numeric(df["Raw Score"], errors='coerce')

    # Check for any remaining NAs
    if df["Raw Score"].isna().any():
        print(f"⚠️ Warning: Found {df['Raw Score'].isna().sum()} rows with NaN scores. Dropping them for plots.")
        df = df.dropna(subset=["Raw Score"])

    # =========================================================================
    # 1. Generate Heatmap (Model vs. Image)
    # =========================================================================
    print("🎨 Generating Heatmap...")
    
    # Pivot the data: Rows=Model, Cols=Image, Values=Score
    pivot = df.pivot_table(
        index="Model", 
        columns="Image", 
        values="Raw Score", 
        aggfunc="mean"
    )

    # Create plot
    plt.figure(figsize=(max(12, len(pivot.columns) * 1.5), max(8, len(pivot.index) * 0.8)))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn",     # Red (Low) to Green (High)
        linewidths=0.5,
        vmin=1,            # Fixed scale 1-5
        vmax=5
    )
    
    plt.title("Mean Recommendation Score (1-5)\nBy Model and Image", fontsize=16, pad=20)
    plt.xlabel("Image", fontsize=12)
    plt.ylabel("Model", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    
    plt.savefig(OUTPUT_HEATMAP, dpi=150)
    plt.close()
    print(f"✅ Saved {OUTPUT_HEATMAP}")

    # =========================================================================
    # 2. Generate Delta Chart (Skepticism Gap)
    # =========================================================================
    print("🎨 Generating Delta Chart...")

    # Calculate means for each condition
    try:
        naive_scores = df[df["Condition"] == "AVERAGE_CONSUMER"].groupby("Model")["Raw Score"].mean()
        critical_scores = df[df["Condition"] == "CONSUMER_ADVOCATE"].groupby("Model")["Raw Score"].mean()
        
        # Calculate Delta: (Naive - Critical)
        # Positive = Model successfully lowered score when warned
        delta = (naive_scores - critical_scores).sort_values(ascending=False)
        
        if delta.empty:
            print("⚠️ No matching model pairs found for Delta Chart.")
        else:
            # Create Bar Chart
            plt.figure(figsize=(12, 6))
            
            # Color bars: Green for Positive (Success), Red for Negative (Backfire)
            colors = ["#2ecc71" if x > 0 else "#e74c3c" for x in delta.values]
            
            bars = plt.bar(delta.index, delta.values, color=colors, edgecolor="black", alpha=0.8)
            
            plt.axhline(0, color="black", linewidth=1)
            plt.title("Skepticism Delta (Naive Score - Critical Score)\nPositive = Model Successfully Reduced Trust", fontsize=14, pad=15)
            plt.ylabel("Score Drop (Points)", fontsize=12)
            plt.xlabel("Model", fontsize=12)
            plt.xticks(rotation=45, ha="right")
            
            # Add value labels on top of bars
            for bar in bars:
                height = bar.get_height()
                plt.text(
                    bar.get_x() + bar.get_width()/2., 
                    height + (0.1 if height > 0 else -0.3),
                    f'{height:.2f}',
                    ha='center', va='bottom', fontsize=10, fontweight='bold'
                )

            plt.tight_layout()
            plt.savefig(OUTPUT_DELTA, dpi=150)
            plt.close()
            print(f"✅ Saved {OUTPUT_DELTA}")

    except Exception as e:
        print(f"❌ Error generating Delta Chart: {e}")

if __name__ == "__main__":
    generate_visualizations()