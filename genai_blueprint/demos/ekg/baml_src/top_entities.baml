
enum Industry {
    Ressources_and_services @alias("Resources and Services")
    PSD @alias("Public Sector and Defense")
    FSI @alias("Financial Services and Insurance")
    Manuf @alias("Manufacturing, MRT") @description("Manufacturing, abreviated as MRT. Include Spatial sector")
    Telco @alias("Telecom, Media and Technology")
    Health @alias("Health and Life Sciences")
}

enum KnownCompetitor {
    Cap @description("Capgemini or subsidary is mentionned")
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
