// Root schema for extracting structured data from a Software Architecture document


enum TechnicalComponentType {
  Languages  @description("Programming languages (e.g., 'Java', 'Python', 'Go').")
  Frameworks  @description("Frameworks/runtimes (e.g., 'Spring Boot', '.NET', 'Node.js').")
  Frontend  @description("Web/mobile UI frameworks and toolchains (e.g., 'React', 'Angular').")
  Backend  @description("Backend frameworks or platforms (e.g., 'Express', 'FastAPI').")
  Databases  @description("Database technologies (e.g., 'PostgreSQL', 'MongoDB').")
  Messaging  @description("Event/messaging tech (e.g., 'Kafka', 'RabbitMQ').")
  Cloud_providers  @description("Cloud platforms (e.g., 'AWS', 'Azure', 'GCP').")
  Containers  @description("Container and image technologies (e.g., 'Docker', 'Buildpacks').")
  Orchestration  @description("Orchestration (e.g., 'Kubernetes', 'ECS').")
  Serverless  @description("Serverless runtimes/services (e.g., 'AWS Lambda').")
  Devops_tools  @description("CI/CD and DevOps tools (e.g., 'GitHub Actions', 'Jenkins').")
  Iac_tools  @description("Infrastructure-as-Code tools (e.g., 'Terraform', 'Bicep').")
  Observability  @description("Monitoring/logging/tracing (e.g., 'Prometheus', 'Grafana', 'ELK').")
  Security_tools  @description("Security tooling (e.g., 'Vault', 'Snyk', 'Inspec').")
  Ai_ml  @description("AI/ML frameworks/services (e.g., 'TensorFlow', 'SageMaker, ChatGPT, Agentic AI, LangChain').")
  Authentication  @description("AuthN services/mechanisms (e.g., 'OIDC', 'Okta').")
  Authorization  @description("AuthZ patterns/systems (e.g., 'RBAC', 'ABAC').")
  Networking  @description("Networking/proxy/CDN tech (e.g., 'Nginx', 'CloudFront').")
  Other  @description("Any other notable technologies.")
}
class TechnicalComponent {
  @@description("Technologies, platforms, and tools referenced in the architecture.")
  name string 
  type TechnicalComponentType

  p_purpose_ string @description("role of the component in the architecture")
}

class SWArchitectureDocument {
    @@description("Normalized schema for extracting key information from a software architecture document")

    opportunity Opportunity @description("Primary project identifier")
    document_date string? @description("Publication or last-update date in ISO 8601 format YYYY-MM-DD.")
   // business_context BusinessContext? @description("Summary, business drivers, goals, KPIs, and constraints motivating the architecture.")

    technical_stack TechnicalComponent[]? @description("Technologies, platforms, frameworks, runtimes, and tools referenced in the solution.")
    used_solutions Solution[]? @description("Named products, managed services, or OSS solutions used and their roles.")
   // architecture ArchitectureOverview? @description("High-level structure, views, patterns, and style of the system.")
    keywords string[]? @description("Keywords/tags extracted for search and similarity (e.g., 'microservices', 'Kafka').")
}


class Solution {
  @@description("Specific product, managed service, or OSS component used in the architecture.")
  name string? @description("Product/solution name (e.g., 'Azure API Management').")
  vendor string? @description("Vendor/organization providing the solution.")
  type string? @description("Category (e.g., 'PaaS', 'SaaS', 'Database', 'Message Broker').")
 
  p_purpose_ string? @description("Role/purpose within the architecture.")
}


function ExtractArchitecture(file: string) -> SWArchitectureDocument {
  client "GptOss120" 
  prompt #"
    Extract from this content:
    {{ file }}

    {{ ctx.output_format }}
  "#
}

function FakeArchitectureJson(project_description: string) -> SWArchitectureDocument {
  client "GptOss120" 
  
  prompt #"
    Generate a fake proposal review for a project descrived as:
    {{ project_description }}

    Follow the format:
    {{ ctx.output_format }}

    JSON:
  "#
}

