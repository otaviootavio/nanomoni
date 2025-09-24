import pandas as pd
import re
import sys


def analyze_logs(file_path):
    """
    Analyzes a log file to extract ECDSA timing information,
    then calculates and prints the average and standard deviation for each function,
    grouped by the service name.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            log_data = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

    # --- Data Extraction ---
    # Regex to find lines with [ECDSA-TIME], and capture the service name, function name, and the time in ms.
    # It captures the service name, skips the timestamp, captures the function tag, and then finds the time.
    pattern = re.compile(
        r"^(\S+)\s*\|\s*\[ECDSA-TIME\]\[.*?\]\s*\[(.*?)\]\s*\[(.*?)\]\s*\[(.*?)\]\s*(\d+\.\d+)ms",
        re.MULTILINE,
    )
    matches = pattern.findall(log_data)

    if not matches:
        print("No [ECDSA-TIME] entries were found in the log file.")
        return

    # --- Data Processing ---
    # Create a pandas DataFrame for easy data manipulation and calculation.
    df = pd.DataFrame(
        matches, columns=["service", "function", "method", "path", "time_ms"]
    )
    df["time_ms"] = pd.to_numeric(df["time_ms"])  # Convert time from string to a number

    # Discard the first 100 samples
    df = df.iloc[100:].reset_index(drop=True)

    # --- Data Aggregation (Dataflow Core) ---
    # Group data by service and function name, then calculate the mean (average) and std (standard deviation).
    # .agg() allows running multiple calculations at once.
    results = (
        df.groupby(["service", "function"])["time_ms"]
        .agg(["mean", "std", "count", "min", "max"])
        .reset_index()
    )

    # Improve column names for the final report.
    results.rename(
        columns={
            "mean": "Average (ms)",
            "std": "Std Dev (ms)",
            "count": "Count",
            "min": "Min (ms)",
            "max": "Max (ms)",
        },
        inplace=True,
    )

    # Fill any NaN values in Std Dev with 0 (this happens for functions with only one entry).
    results.fillna(0, inplace=True)

    # --- Data Presentation ---
    # Print the final results in a clean, formatted table.
    print("--- ECDSA Timing Analysis ---")
    with pd.option_context(
        "display.max_rows", None, "display.max_columns", None, "display.width", 1000
    ):
        print(results.to_string(index=False))
    print("---------------------------")


if __name__ == "__main__":
    # The script expects the log file to be named "out.txt" in the same directory.
    log_file = "out.txt"
    analyze_logs(log_file)
