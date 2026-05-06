#!/usr/bin/env python3
"""
VLLM Integration Demo for GenAI-Blueprint

This script demonstrates how to use the VLLM endpoint integration with the GenAI-Blueprint framework.

Prerequisites:
1. Install vLLM: pip install vllm
2. Ensure you have a CUDA-compatible GPU (for local inference)
3. Download the model you want to use (or use HuggingFace Hub)

Usage:
    python examples/vllm_demo.py

Note: This demo shows the configuration and setup. Actual model inference requires
GPU resources and model downloads which may take significant time and storage.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from genai_tk.core.factories.llm_factory import LlmFactory, get_llm_info


def demo_vllm_configuration():
    """Demonstrate VLLM model configuration retrieval."""
    print("🚀 VLLM Integration Demo for GenAI-Blueprint")
    print("=" * 50)

    # Get all available VLLM models
    all_llms = LlmFactory.known_list()
    vllm_models = [llm for llm in all_llms if llm.provider == "vllm"]

    print(f"📋 Found {len(vllm_models)} VLLM models configured:")
    for model in vllm_models:
        print(f"  • {model.id}")
        print(f"    Model: {model.model}")
        print(f"    Args: {model.llm_args}")
        print()


def demo_vllm_factory():
    """Demonstrate VLLM factory usage."""
    print("🏭 VLLM Factory Demo")
    print("-" * 30)

    # Example model ID (you can change this to any VLLM model from the config)
    model_id = "mpt_7b_vllm_vllm"

    try:
        # Get model information
        info = get_llm_info(model_id)
        print(f"📊 Model Info for {model_id}:")
        print(f"  Provider: {info.provider}")
        print(f"  Model: {info.model}")
        print(f"  Parameters: {info.llm_args}")
        print()

        # Create factory (this doesn't instantiate the actual model)
        factory = LlmFactory(llm_id=model_id)
        print(f"🏭 Factory created successfully for {factory.short_name()}")
        print(f"  Provider: {factory.provider}")
        print()

        # Check if vLLM is available
        try:
            import vllm

            print("✅ vLLM package is available")
            print("📝 To actually use the model, you would call:")
            print(f"   llm = get_llm(llm_id='{model_id}')")
            print("   response = llm.invoke('Your prompt here')")
            print()
            print("⚠️  Note: This requires GPU resources and model download")

        except ImportError:
            print("❌ vLLM package not installed")
            print("💡 Install with: pip install vllm")

    except Exception as e:
        print(f"❌ Error: {e}")


def demo_vllm_usage_example():
    """Show example usage code."""
    print("💡 Example Usage Code")
    print("-" * 30)

    example_code = """
# Example: Using VLLM with GenAI-Blueprint
from genai_tk.core.factories.llm_factory import get_llm

# Method 1: Direct model specification
llm = get_llm(llm_id="mpt_7b_vllm_vllm")

# Method 2: With custom parameters
llm = get_llm(
    llm_id="llama32_3b_vllm_vllm",
    temperature=0.8,
    max_tokens=256
)

# Method 3: Using in a chain
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_template("Explain {topic} in simple terms.")
chain = prompt | llm

# Generate response
response = chain.invoke({"topic": "machine learning"})
print(response.content)

# Method 4: Streaming response
llm_streaming = get_llm(llm_id="mpt_7b_vllm_vllm", streaming=True)
for chunk in llm_streaming.stream("Tell me about AI"):
    print(chunk.content, end="", flush=True)
"""

    print(example_code)


def main():
    """Main demo function."""
    demo_vllm_configuration()
    demo_vllm_factory()
    demo_vllm_usage_example()

    print("🎉 VLLM integration demo completed!")
    print("📚 For more information, see:")
    print("  • LangChain VLLM docs: https://python.langchain.com/docs/integrations/llms/vllm/")
    print("  • VLLM GitHub: https://github.com/vllm-project/vllm")
    print("  • GenAI-Blueprint docs: config/providers/llm.yaml")


if __name__ == "__main__":
    main()
