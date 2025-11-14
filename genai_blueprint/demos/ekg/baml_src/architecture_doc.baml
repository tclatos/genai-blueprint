// Root schema for extracting structured data from a Software Architecture document
class SWArchitectureDocument {
    @@description("Normalized schema for extracting key information from a software architecture document")

    opportunity Opportunity @description("Primary project identifier")
    document_date string? @description("Publication or last-update date in ISO 8601 format YYYY-MM-DD.")
    business_context BusinessContext? @description("Summaru, business drivers, goals, KPIs, and constraints motivating the architecture.")

    technical_stack TechnicalStack? @description("Technologies, platforms, frameworks, runtimes, and tools referenced in the solution.")
    used_solutions Solution[]? @description("Named products, managed services, or OSS solutions used and their roles.")
    architecture ArchitectureOverview? @description("High-level structure, views, patterns, and style of the system.")
    components Component[]? @description("Primary components/services/modules and their responsibilities.")
    interfaces Interface[]? @description("APIs, events, queues, topics, and other integration interfaces.")
    data_stores DataStore[]? @description("Databases, data lakes, caches, object stores, and schemas.")
    integrations Integration[]? @description("External/internal systems integrated with, including direction and contracts.")
    deployment Deployment? @description("Environments, topology, regions, CI/CD, IaC, scaling, and DR strategy.")
    security Security? @description("Security model, controls, data handling, and identity strategy.")
    compliance Compliance? @description("Regulatory and standards compliance requirements and posture.")
    operations Operations? @description("Monitoring, logging, alerting, runbooks, SLOs/SLAs, and reliability practices.")
    // testing Testing? @description("Test strategy, coverage, types, tools, and quality gates.")
    //decisions Decision[]? @description("Architectural decisions (ADR-style), rationale, and consequences.")
    risks Risk[]? @description("Key risks with impact, likelihood, mitigation, and status.")
    //assumptions Assumption[]? @description("Stated or implied assumptions that influence the design.")
    //references Reference[]? @description("Standards, specs, tickets, repos, and external documents referenced.")
    keywords string[]? @description("Keywords/tags extracted for search and similarity (e.g., 'microservices', 'Kafka').")
    //notes string? @description("Miscellaneous notes or unstructured details relevant to extraction.")
}



// Business and requirements
class BusinessContext {
  @@description("Business drivers and success criteria that shape the architecture.")
  overview string? @description("Narrative of the business problem and context.")
  objectives string[]? @description("Explicit business objectives/goals.")
  kpis KPIMetric[]? @description("Key performance indicators and targets.")
  timeline string? @description("Important dates/milestones (e.g., launch, compliance deadlines).")
  budget_range string? @description("Budgetary constraints if specified (e.g., '$100k–$300k').")
}

class KPIMetric {
  @@description("Quantitative or qualitative KPI with a target and measurement method.")
  name string? @description("KPI name (e.g., 'Checkout conversion', 'MTTR').")
  target string? @description("Target value or threshold (e.g., '≥ 99.95%', '≤ 10 min').")
  measurement string? @description("How the KPI is measured, including data source and cadence.")
}

class Requirements {
  @@description("Functional and non-functional requirements for the system.")
  functional_overview string? @description("Summary of core capabilities and user value.")
  user_stories string[]? @description("Representative user stories or use cases.")
  acceptance_criteria string[]? @description("Key acceptance criteria if stated.")
  non_functional NonFunctionalRequirement[]? @description("NFRs such as performance, security, availability.")
}

class NonFunctionalRequirement {
  @@description("Single non-functional requirement with a measurable target.")
  category string? @description("Category (e.g., 'Performance', 'Availability', 'Security').")
  statement string? @description("Requirement statement (e.g., 'P95 latency ≤ 200 ms').")
  rationale string? @description("Reason the NFR is required.")
  verification string? @description("How the NFR will be validated or monitored.")
}

class Constraint {
  @@description("Constraint that limits solution space.")
  category string? @description("Type (e.g., 'Regulatory', 'Technology', 'Vendor', 'Budget', 'Timeline').")
  description string? @description("Constraint detail (e.g., 'Must run on Azure', 'No PII export outside EU').")
  source string? @description("Origin of constraint (e.g., 'Legal', 'Customer policy', 'Legacy').")
}

// Technology and solutions
class TechnicalStack {
  @@description("Technologies, platforms, and tools referenced in the architecture.")
  languages string[]? @description("Programming languages (e.g., 'Java', 'Python', 'Go').")
  frameworks string[]? @description("Frameworks/runtimes (e.g., 'Spring Boot', '.NET', 'Node.js').")
  frontend string[]? @description("Web/mobile UI frameworks and toolchains (e.g., 'React', 'Angular').")
  backend string[]? @description("Backend frameworks or platforms (e.g., 'Express', 'FastAPI').")
  databases string[]? @description("Database technologies (e.g., 'PostgreSQL', 'MongoDB').")
  messaging string[]? @description("Event/messaging tech (e.g., 'Kafka', 'RabbitMQ').")
  cloud_providers string[]? @description("Cloud platforms (e.g., 'AWS', 'Azure', 'GCP').")
  containers string[]? @description("Container and image technologies (e.g., 'Docker', 'Buildpacks').")
  orchestration string[]? @description("Orchestration (e.g., 'Kubernetes', 'ECS').")
  serverless string[]? @description("Serverless runtimes/services (e.g., 'AWS Lambda').")
  devops_tools string[]? @description("CI/CD and DevOps tools (e.g., 'GitHub Actions', 'Jenkins').")
  iac_tools string[]? @description("Infrastructure-as-Code tools (e.g., 'Terraform', 'Bicep').")
  observability string[]? @description("Monitoring/logging/tracing (e.g., 'Prometheus', 'Grafana', 'ELK').")
  security_tools string[]? @description("Security tooling (e.g., 'Vault', 'Snyk', 'Inspec').")
  ai_ml string[]? @description("AI/ML frameworks/services (e.g., 'TensorFlow', 'SageMaker').")
  authentication string[]? @description("AuthN services/mechanisms (e.g., 'OIDC', 'Okta').")
  authorization string[]? @description("AuthZ patterns/systems (e.g., 'RBAC', 'ABAC').")
  networking string[]? @description("Networking/proxy/CDN tech (e.g., 'Nginx', 'CloudFront').")
  other string[]? @description("Any other notable technologies.")
}

class Solution {
  @@description("Specific product, managed service, or OSS component used in the architecture.")
  name string? @description("Product/solution name (e.g., 'Azure API Management').")
  vendor string? @description("Vendor/organization providing the solution.")
  type string? @description("Category (e.g., 'PaaS', 'SaaS', 'Database', 'Message Broker').")
  edition string? @description("Edition/tier if specified (e.g., 'Enterprise', 'Standard').")
  version string? @description("Version or release (e.g., 'v3.2.1').")
  deployment_model string? @description("Host/deployment model (e.g., 'Managed', 'Self-hosted').")
  purpose string? @description("Role/purpose within the architecture.")
}

// Architecture views and structure
class ArchitectureOverview {
  @@description("High-level architecture style and views.")
  style string? @description("Overall style/pattern (e.g., 'Microservices', 'Layered', 'Event-driven', 'Hexagonal').")
  patterns string[]? @description("Architectural patterns (e.g., 'CQRS', 'Saga', 'Strangler Fig').")
  context string? @description("System context and boundaries; C4 Level 1 summary if present.")
  domain_model string? @description("Domain model or bounded contexts overview.")
  quality_attributes string[]? @description("Primary quality attributes prioritized by the design.")
}

class Component {
  @@description("Logical or deployable unit within the system.")
  name string? @description("Component/service/module name.")
  type string? @description("Type (e.g., 'Service', 'Web App', 'Batch Job', 'Library').")
  responsibilities string[]? @description("Key responsibilities or capabilities.")
  technology string? @description("Primary technology used by the component.")
  inbound_interfaces string[]? @description("Consumed interfaces (APIs/events) with brief notes.")
  outbound_interfaces string[]? @description("Exposed interfaces (APIs/events) with brief notes.")
  data_owned string[]? @description("Canonical data/entities owned by the component.")
  dependencies string[]? @description("Direct dependencies on other components or services.")
  availability_tier string? @description("Availability class/expectation (e.g., 'Tier 0', '99.9%').")
  scaling_model string? @description("Horizontal/vertical/auto-scaling characteristics.")
}

class Interface {
  @@description("API, event, message, or protocol-based interface.")
  name string? @description("Interface name or identifier.")
  direction string? @description("Provider or consumer perspective (e.g., 'Exposed', 'Consumed').")
  style string? @description("Interaction style (e.g., 'REST', 'GraphQL', 'gRPC', 'Event', 'Queue').")
  transport_protocol string? @description("Protocol/transport (e.g., 'HTTPS', 'AMQP', 'Kafka').")
  endpoint string? @description("Endpoint/URI/topic/queue where applicable.")
  auth string? @description("Auth mechanism (e.g., 'OAuth2', 'mTLS').")
  schema string? @description("Schema or contract reference (e.g., 'OpenAPI v3', 'Avro').")
  qos string? @description("QoS/reliability semantics (e.g., 'At-least-once', 'Idempotent').")
}

class DataStore {
  @@description("Logical or physical data store used by the solution.")
  name string? @description("Data store name.")
  type string? @description("Type/category (e.g., 'RDBMS', 'NoSQL', 'Cache', 'Data Lake', 'Object Storage').")

}

// Integration and deployment
class Integration {
  @@description("Connection to an external or internal system.")
  name string? @description("Name of external/internal system.")

  p_comment_ string @description("Description of the integration.")

}

class Deployment {
  @@description("How the system is deployed and operated across environments.")
  environments Environment[]? @description("Named environments (e.g., 'Dev', 'QA', 'Prod') with details.")
  regions string[]? @description("Cloud or data center regions used.")
  topology string? @description("Deployment topology (e.g., 'Active-Active', 'Active-Passive').")
  ci_cd string? @description("CI/CD pipelines and release strategy.")
  iac string? @description("IaC approach and repositories (e.g., 'Terraform modules').")
  scaling_strategy string? @description("Autoscaling rules and capacity planning notes.")
  disaster_recovery string? @description("DR strategy, failover, and testing cadence.")
}

class Environment {
  @@description("Single environment's operational characteristics.")
  name string? @description("Environment name (e.g., 'Dev', 'Staging', 'Prod').")
  purpose string? @description("Primary purpose (testing, performance, UAT, etc.).")
  region string? @description("Primary region/location for this environment.")
  network_zone string? @description("Network/VPC/VNet details or identifier.")
  compute_profile string? @description("Cluster/instances/nodes profile description.")
}

// Security, compliance, and operations
class Security {
  @@description("Security considerations and controls.")
  data_classification string? @description("Classification scheme and data categories handled.")
  encryption_in_transit string? @description("TLS/mTLS settings, protocols, and policies.")
  encryption_at_rest string? @description("Storage encryption mechanisms and key scope.")
  key_management string? @description("KMS/HSM and key rotation policies.")
  identity_access_mgmt string? @description("IAM model, roles, groups, and least-privilege strategy.")
  secrets_management string? @description("Secrets handling and storage (e.g., 'Vault', 'KMS').")
  vulnerability_mgmt string? @description("Vulnerability scanning/patching processes and SLAs.")
  threat_model string? @description("Summary of threat modeling outcomes or references.")
}

class Compliance {
  @@description("Regulatory requirements and adherence.")
  standards string[]? @description("Applicable standards/frameworks (e.g., 'PCI DSS', 'HIPAA', 'SOC 2').")
  data_residency string? @description("Data residency/localization requirements.")
  audit_requirements string? @description("Audit logging/retention and evidence expectations.")
  controls_summary string? @description("Key controls and responsible parties.")
}

class Operations {
  @@description("Operational readiness and reliability engineering aspects.")
  monitoring_tools string[]? @description("Monitoring/metrics tools used.")
  logging string? @description("Centralized logging approach and retention.")
  alerting string? @description("Alerting rules, on-call, and escalation paths.")
  runbooks string[]? @description("Runbooks/SOPs references.")
  slos SLO[]? @description("Service Level Objectives and targets.")
  slas SLA[]? @description("Customer-facing Service Level Agreements if defined.")
}

class SLO {
  @@description("Service Level Objective for a service or capability.")
  name string? @description("SLO name (e.g., 'Checkout availability').")
  target string? @description("Target such as '99.9% monthly' or 'P95 < 200 ms'.")
  measurement string? @description("Measurement window and method.")
}

class SLA {
  @@description("Service Level Agreement commitments.")
  metric string? @description("Metric (e.g., 'Uptime', 'Support response').")
  commitment string? @description("Committed level (e.g., '99.95% monthly').")
  penalties string? @description("Credits/penalties for breach if stated.")
}

// Decisions, risks, and assumptions
class Decision {
  @@description("Architectural decision (ADR-style).")
  id string? @description("Decision identifier (e.g., 'ADR-001').")
  date string? @description("Decision date in ISO 8601 format YYYY-MM-DD.")
  title string? @description("Short decision title.")
  status string? @description("Status (e.g., 'Proposed', 'Accepted', 'Superseded').")
  context string? @description("Context/problem statement motivating the decision.")
  options string[]? @description("Options considered.")
  decision string? @description("Chosen option and summary.")
  rationale string? @description("Why this option was chosen.")
  consequences string[]? @description("Positive/negative consequences of the decision.")
}

class Risk {
  @@description("Risk item with likelihood and impact.")
  id string? @description("Risk identifier (e.g., 'R-12').")
  description string? @description("Risk description.")
  impact string? @description("Impact level or narrative (e.g., 'High', 'Service outage').")
  likelihood string? @description("Likelihood (e.g., 'Low', 'Medium', 'High').")
  mitigation string? @description("Mitigation/response plan.")
  owner Person? @description("Person responsible for tracking the risk.")
  status string? @description("Status (e.g., 'Open', 'Mitigated', 'Accepted').")
}

class Assumption {
  @@description("Assumption that influences the architecture.")
  description string? @description("Assumed condition or dependency.")
  source string? @description("Origin or rationale for the assumption.")
}

// Artifacts and references
class Diagram {
  @@description("Diagram or model referenced by the document.")
  title string? @description("Diagram title.")
  type string? @description("Type (e.g., 'C4-Context', 'Sequence', 'Deployment').")
  reference string? @description("File name, doc anchor, or repo path/id.")
  url string? @description("URL if available for retrieval.")
}

class Reference {
  @@description("External reference or source.")
  title string? @description("Reference title/description.")
  type string? @description("Type (e.g., 'Spec', 'Repo', 'Ticket', 'Standard').")
  url string? @description("Reference URL or identifier.")
  notes string? @description("Any relevant notes about the reference.")
}

class GlossaryTerm {
  @@description("Defined term used in the document.")
  term string? @description("Term or acronym.")
  definition string? @description("Definition as used in this context.")
  synonyms string[]? @description("Synonyms or related terms.")
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

