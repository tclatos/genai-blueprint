
client<llm> DeepseekChat {
  provider "openai-generic"
  options {
    temperature 0.0
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "deepseek/deepseek-chat-v3.1"
    headers {
    }
  }
}


client<llm> Gpt41mini {
  provider "openai-generic"
  options {
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "gpt-4.1-mini"
    temperature 0.0
    headers {
    }
  }
}

client<llm> GptOss120 {
  provider "openai-generic"

  options {
    temperature 0.0
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "openai/gpt-oss-120b"
    headers {
    }
  }
}
