
enum Industry {
    Ressources_and_services @alias("i1") @description("Resources and Services")
    PSD @alias("i2") @description("Public Sector and Defense")
    FSI @alias("i3") @description("Financial Services and Insurance")
    Manuf @alias("i4") @description("Manufacturing, abreviated as MRT. Include Spatial sector")
    Telco @alias("i5") @description("Telecom, Media and Technology")
    Health @alias("i6") @description("Health and Life Sciences")
}

// see https://docs.boundaryml.com/examples/prompt-engineering/symbol-tuning not verified
enum KnownCompetitor {
    Capgemini @alias("c1") @description("Capgemini (abreviated CAP) or subsidary is mentionned")
    Thales @description("Thales Group or subsidary is mentionned")
    IBM @description("IBM of subsidary is mentionned")
    Accenture @description("Accenture or subsidary is mentionned")
    DXC @description("DXC Technology or subsidary is mentionned")
    TCS @description("Tata Consultancy Services (commonly abreaviated as TCS) or subsidary is mentionned")
    Infosys @description("Infosys Limited or subsidary is mentionned")
    Wipro @description("Wipro Limited or subsidary is mentionned")
    Cognizant @description("Cognizant Technology or subsidary is mentionned")
    HCL @description("HCL Technologies or subsidary is mentionned")
    CGI @description("CGI Inc. or subsidary is mentionned")
    Sopra @description("Sopra Steria or subsidaryis mentionned")
    CS @description("CS GROUP (commonly abreaviated as CS) or subsidary  is mentionned" )
   // Other @description("Other Competitors are mentionned")
}

class Opportunity {
  name string @description("Official name of the project/opportunity")
  opportunity_id string @description("Unique identifier from Salesforce or similar CRM")
  status OpportunityStatus? @description("Current phase: Pursuit/Active/Completed/Cancelled")
  customer Customer @description("Client or customer information")
}

class Person {
  @@description("person involved in a project")
  name string? @description("Full name of involved person")
  organization string? @description("Affiliated organization")
  contact_type string? @description("Internal/External/Client/Partner")

  p_role_ string? @description("Formal role in project")
}

class Customer {
  name string  @description("Client organization name")
  segment string? @description("Industry vertical of the customer")
  employees Person[]?  @description("Customer's employees mentionned in the document. Do not include Atos or other people")
}


class Partner {
  name string
  p_role_ string? @description("role in the project")
}

