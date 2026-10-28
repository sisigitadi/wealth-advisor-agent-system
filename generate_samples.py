"""
Quick script to generate sample JSON output files for review.
Run: python generate_samples.py
"""

import os
import sys

from wealth_advisor_agent import WealthAdvisorOrchestrator

output_dir = os.path.join(os.path.dirname(__file__), "sample_output")
os.makedirs(output_dir, exist_ok=True)

for client_id in ["CLIENT_1001", "CLIENT_1002"]:
    temp_mem = os.path.join(output_dir, f"{client_id.lower()}_temp_mem.json")
    orch = WealthAdvisorOrchestrator(auto_approve=True, memory_path=temp_mem)
    output = orch.process_client_review(client_id)

    filepath = os.path.join(output_dir, f"{client_id.lower()}_output.json")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Generated: {filepath}", file=sys.stderr)

    if os.path.exists(temp_mem):
        os.remove(temp_mem)

print("Done! Check sample_output/ directory.", file=sys.stderr)
