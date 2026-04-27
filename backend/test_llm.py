import asyncio
import os
import json
import logging
from dotenv import load_dotenv

# Setup minimal logging to view output
logging.basicConfig(level=logging.INFO)

# Load env variables including the new API keys
load_dotenv(dotenv_path=".env")

from app.services.llm.orchestrator import LLMOrchestrator

async def run_test():
    print("Initializing Orchestrator...")
    orchestrator = LLMOrchestrator()
    
    sample_transcript = """
    Agent: Hello, thank you for calling Aegis Support. How can I help you today?
    Customer: Hi, I've been trying to log into my account for three days, and it keeps saying 'invalid password' even though I just reset it! I'm getting really annoyed.
    Agent: I apologize for the inconvenience. Let me check your account status. Can I have your email?
    Customer: It's john.doe@example.com. Honestly, if this doesn't get fixed today, I'm just going to cancel my subscription and go to Competitor X. Their app actually works.
    Agent: I completely understand your frustration, John. I see the issue here. There was a synchronization delay with our new password server. I have manually synced it now.
    Customer: Okay, let me try... Ah, it works now. Finally. Thanks.
    Agent: You're very welcome. Is there anything else I can assist you with?
    Customer: No, that's it. Have a good day.
    """
    
    print("Running LLM analysis (Should hit Gemini or Mistral)...")
    result = orchestrator.analyze_transcript(
        session_id="test_session_123",
        transcript_text=sample_transcript,
        num_speakers=2,
        duration_seconds=45.0,
    )
    
    if result:
        print("\n=== TEST SUCCESSFUL ===")
        print(f"Model Used: {result.model_used}")
        print(f"Executive Summary: {result.executive_summary}")
        print("\nMetrics 7-Scale:")
        print(json.dumps(result.global_metrics_7_scale, indent=2))
        print(f"\nSegments Analyzed: {len(result.segment_by_segment_analysis)}")
        
        if result.segment_by_segment_analysis:
            print("\nFirst Segment Params Extract:")
            print(json.dumps(result.segment_by_segment_analysis[0].get("twenty_parameters", {}), indent=2))
            
    else:
        print("\n=== TEST FAILED (Returned None) ===")

if __name__ == "__main__":
    asyncio.run(run_test())
