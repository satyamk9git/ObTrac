"""
ObTrac SDK — Quickstart Example
Minimal setup to trace any Python function.

pip install obtrac-sdk
"""

from obtrac_sdk import obtrac_config, trace, observe

# Step 1: Configure (once at top — no cost here, cost goes in @trace)
config = obtrac_config(
    project="quickstart",
    backend_url="http://localhost:8100",
    user="satyam",
)

# Step 2: Decorate your functions — cost is per-decorator (different models = different costs)
@trace(name="fetch_data", span_type="retrieval")
def fetch_data(query: str) -> list[str]:
    return [f"Result 1 for {query}", f"Result 2 for {query}"]


@trace(name="process", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def process(data: list[str]) -> str:
    return f"Processed: {', '.join(data)}"


@observe(name="my_pipeline")
def pipeline(query: str) -> str:
    data = fetch_data(query)
    result = process(data)
    return result


# Step 3: Run — traces sent to ObTrac dashboard
if __name__ == "__main__":
    answer = pipeline("test query")
    print(f"Answer: {answer}")
    print("View at: http://localhost:3100")
