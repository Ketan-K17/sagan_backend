import os
from smolagents import ToolCallingAgent, HfApiModel
from dotenv import load_dotenv
import sys

def main():
    # Load environment variables (should contain HUGGINGFACE_API_KEY)
    load_dotenv()
    
    # Check if HUGGINGFACEHUB_API_TOKEN is set
    if "HUGGINGFACEHUB_API_TOKEN" not in os.environ:
        print("Error: HUGGINGFACEHUB_API_TOKEN environment variable not set")
        print("Please set this in a .env file or your environment")
        sys.exit(1)
    
    print("Starting SmolaGents HuggingFace API Test...")
    
    # Choose a model to test
    # model_id = "meta-llama/Llama-3.3-70B-Instruct"  # Large model
    model_id = "meta-llama/Llama-3.3-70B-Instruct"  # Smaller model for testing
    print(f"Using model: {model_id}")
    
    try:
        # Initialize the model
        model = HfApiModel(model_id=model_id)
        print("✅ Model initialized successfully")
        
        # Create a simple agent without tools
        agent = ToolCallingAgent(
            model=model, 
            tools=[], 
            prompt_templates={"system_prompt": "You are a helpful assistant."}
        )
        print("✅ Agent created successfully")
        
        # Test a simple query
        test_prompt = "Tell me who Roger Federer is."
        print(f"\nTesting with prompt: '{test_prompt}'")
        
        # Get response
        response = agent.provide_final_answer(test_prompt, images=None)
        
        print("\n--- Response from model ---")
        print(response)
        print("---------------------------")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("Test failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
