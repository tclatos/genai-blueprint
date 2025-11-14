enum OpportunityStatus {
    Pursuit
    Active
    Completed
    Cancelled
}


enum SWProjectRisks {
    ScheduleRisk @description("Occurs when the project timeline is underestimated, leading to delays and potential cost overruns.")
    BudgetRisk @description("Arises when the project exceeds its allocated budget, often due to unforeseen expenses or poor financial planning.")
    ScopeCreep @description("Refers to the gradual expansion of project scope without corresponding adjustments in time, budget, or resources.")
    TechnicalDebt @description(#"
        Accumulates when shortcuts are taken in code development, leading to future challenges in maintenance and scalability.
        It can result in increased costs and time for future modifications and improvements."#)
    ResourceAvailability @description("Occurs when necessary resources, such as personnel or equipment, are not available when needed, impacting project progress.")
    QualityRisk @description("Involves the potential for the final product to not meet the required standards or specifications, affecting user satisfaction.")
    StakeholderAlignment @description("Happens when stakeholders have conflicting interests or expectations, leading to project misdirection or disputes.")
    IntegrationChallenges @description(#"
        Arises when integrating new software with existing systems, potentially causing compatibility issues or data inconsistencies.
        This risk can lead to delays and additional costs in resolving integration problems."#)
    SecurityVulnerabilities @description("Involves the risk of exposing sensitive data or systems to unauthorized access, requiring robust security measures.")
    RegulatoryCompliance @description("Concerns the need to adhere to legal and regulatory requirements, which can impact project scope and timelines.")
    SLAComplianceRisk @description(#"
        Involves the application of penalties due to non-compliance with Service Level Agreements (SLAs) resulting from quality issues or delivery delays.
        This risk can lead to financial losses and damage to client relationships."#)
    DeliveryCostOverrun @description(#"
        Arises from underestimation of delivery costs, often due to re-deliveries, missing packages, and non-representative platforms.
        This risk can result in budget overruns and financial strain on the project."#)
    ScopeManagementRisk @description(#"
        Concerns the challenges of handling non-mastered subjects or overly broad scopes due to minimal transition on Venus/VIP and intermediate transition on THEIA/MUSCATE.
        This can lead to quality issues, delays, and cost overruns."#)
    SkillRetentionRisk @description(#"
        Involves difficulties in maintaining necessary skills due to high turnover and decreasing activity levels.
        This risk can impact project quality, timelines, and costs, as experienced personnel are crucial for project success."#)
}

class ReviewedOpportunity {
  opportunity Opportunity
  start_date string? @description("Planned/projected start date")
  keywords string[]? @description("Key terms for semantic search")
  tech_stack TechnicalApproach @description("Architecure and technology choices")

  // statement_of_work KeyStatementOfWorkElement? @description("Business approach to win the opportunity")
  team Person[] @description("Atos or Eviden person involved")  
  financials FinancialMetrics @description("Financial metrics")
  risks RiskAnalysis[] @description("Risk analysis")
  competition CompetitiveLandscape @description("Competitive landscape")
  competitors Competitor[]? @description("Identified competitors for that opportunity")
  // bidding BiddingStrategy @description("Bidding strategy")
  partners Partner[]? @description("Third-party partners/subcontractors")

  //competitor_map map<string, Competitor> @description("Identified competitors for that opportunity")

} 
class Competitor {
  @@description("Atos competitor mentionned in the documents. Don't confused with Partners")
  // isa ACompetitor @description("Competitor mentionned in the review")
  name string @description("name of the competitor")
  known_as KnownCompetitor? @description("Competitor id (short name)")

  // Link properties 
  p_comment_ string? @alias("comment") @description("What is said about that competitor (strong points, etc...)")

}

class References {
  @@description ("Atos projects, products and solution referenced in the project")
  name string[] @description("Name of the Atos projects, products and solution referenced in the project")
}
class TechnicalApproach {
  architecture string? @description("General information on architecture")
  technical_stack string[]? @description("technical stack (platforms, frameworks, third-party softwares, programming language, ...)")
}



// class KeyStatementOfWorkElement {
//   objectives string[]? @description("Key business objectives of the project")
//   scope string? @description("Scope of work description")
//   requirements string[]? @description("Key requirements")
//   success_metrics string[]? @description("Measurable success criteria")

// }



// class DeliveryInfo {
//   business_lines string[]? @description("Involved business units")
//   locations string[]? @description("Geographic locations of delivery")

// }

class FinancialMetrics {
  tcv float? @description("Total Contract Value in EUR")
  annual_revenue float? @description("Yearly revenue projection")
  project_margin float? @description("Gross margin percentage")
}

class RiskAnalysis {

  risk_category SWProjectRisks? @description("classification of the risk")

  p_mitigation_strategy_ string? @description("Planned mitigation approach")
  p_risk_description_ string @description("Risk description in the document")
}

class CompetitiveLandscape {
  competitive_position string? @description("Position vs competition")
  differentiators string[]? @description("Unique selling points vs competition")
}

class BiddingStrategy {
  strategy_type string? @description("Prime/Sub/JV bidding strategy")
  win_themes string[]? @description("Key winning strategy elements")
  pricing_strategy string? @description("Cost-led/Value-based pricing")
  challenges string[]? @description("Key bidding challenges")
}



function ExtractRainbow(rainbow_file: string) -> ReviewedOpportunity {
  client "GptOss120" 
  prompt #"
    Extract from this content:
    {{ rainbow_file }}

    {{ ctx.output_format }}
  "#
}

function FakeRainbowJson(project_description: string) -> ReviewedOpportunity {
  client "GptOss120" 
  
  prompt #"
    Generate a fake proposal review for a project descrived as:
    {{ project_description }}

    Follow the format:
    {{ ctx.output_format }}

    JSON:
  "#
}


// test TestFake {
//   functions [GenerateFakeRainbowDoc]
//   args {
//     project_description #"
//     an IT project in the financial services, with a database, Thales and Cap as competitor, and low usual risks"
//   }
// }


// Test the function with a sample resume. Open the VSCode playground to run this.
test rainbow_analysys {
  functions [ExtractRainbow]
  args {
    rainbow_file #"
# Solution Review Slides

## CNES TMA VENUS VIP_PEPS_ THEIA MUSCATE

### Barthélémy MARTI
**24/01/2019 9000559500**

# Objective of this Review Key Decision Points 



Solution | Introduction | Solution | Winning Solution | Way Forward
---|---|---|---|---
|  |  |  |  |  |
| Client - Opportunity |  |  |  |  |
| CNES TMA VENUS VIP, PEPS, THEIA MUSCATE |  |  |  |  |
| Pipeline Characteristics |  |  |  |  |
| Markets/Sectors | MRT Aerospace | CRM Opp. ID | 9000559500 |  |
| Division(s) | B1P S BS Toulouse (100%) |  |  |  |
| Opportunity Type | Fertilisation | Contract Type | Obligation of result |  |
| Contract Duration | 2+36 Months | TCV | 1,8 MK |  |
| Start Date | 01/04/2019 | CV Current Year | 0,3 MK |  |
| Decision Date | 08/03/2019 | Bid Cost | 36 | KK |
| Request Expected |  | Response Due | 30/01/2019 |  |
| Authorization | L5 (Business Unit) | Probability | 30 % |  |
| Reliability |  | Status | 0 |  |
| Scope Description |  |  |  |  |
| Opportunity | TMA des centres de production et de diffusion de données d'observation de la Terre et leur chaîne de traitement d'images associés : PEPS, THEIA MUSCATE et VENUS VIP comprenant une phase de prise de connaissances et une phase de maintenance corrective et évolutive regroupée en 3 lots avec options. L'ensemble est mono attributaire |  |  |  |
| Background & Requirements |  |  |  |  |
| Geographies |  |  |  |  |
| Solution, Transition | Prise de connaissance THEIA MUSCATE, prise de connaissance minimale sur VVENUS VIP, and/or Continuous sous-traitance avec ACS (imposée par le CNES) sur la partie VENUS VIP, PIXTART+SPACE4DEV pour la partie THEIA MUSCATE. Maintenance corrective et évolutive avec une équipe mutualisée |  |  |  |
| Staff Transfer |  | FTEs | Asset Transfer | MK |
| Global Sourcing |  | DTF/CSCs |  |  |
| Partner(s)/Subco(s) | ACS sur partie Venus/PIXSTART sur THEIA | Client Advisor |  |  |
| Accuracy |  | Status | 0 |  |
|  |  | Lead Division - Lead GBU/Country - Deal Sponsor | Updated on
---|---|---|---
|  |  | B&P S GBU FR BS Toulouse C|hristophe BRIZOT | 22/01/2109 |
| Involvement |  |  |  |  |
| (Global) Client Leader | Marc Ferrer | Sales Lead / Deal Maker | Aurore Dorez |
| Bid Manager | Barthélémy Marti | Solution Manager | Olivier Rondeau |
| Finance Lead | Caroline Jaulin/Encarnita Alemany | Deal Lawyer | Danièle Phankongsy |
| HR Lead | N/A | Procurement Lead | Yanide Pseaume |
| Contract Executive | Olivier Rondeau | (T&T) Project Manager | Sonia Gouel |
| Client Contacts & Relation Quality | Pierre Bourrousse - Stratégie Achat - Sponsor Green
|  |  | Gérard Lassalle-Valler Sponsor Green
|  |  | Sylvia Sylvander CP CNES Décideur - Amber |
| Commitment |  | Status | 0 |
| Win Plan |  |  |  |  |
| Atos Differentiators | Présent sur PEPs, Connaissances métiers et des écosystèmes d'observation de la Terre, MUNDI et partenariats |  |  |  |
| Competitors & their Differentiators | CAP : présent sur THEIA MUSCATE + proximité client
|  |  | CS : Venus (volume activité faible) mais réponse complaisance |
| Critical Issues & Mitigations |  | Thales : réponse de complaisance |
| Opportunity Status | Solution |  |  |  |
| Next Steps | Offer |  |  |  |
| Next Rainbow | Offer | Date | 25/01/2019 |  |
| Effectiveness |  | Status | 0 |

Key risks

- Application de pénalités du fait de non respect des SLAs suite à des problèmes de qualité ou de délais de livraison
- Surcout des livraisons du fait de la sous-estimation de ces couts suite à des relivraisons, packages manquants et des problèmes de non représentativité de nos plateformes
- Problèmes à traiter sur sujets non maitrisés ou un périmètre trop grand du fait de la transition minimum sur Venus/VIP \& intermédiaire sur THEIA/MUSCATE induisant des problèmes de qualité, délai et surcout
- Difficultés à maintenir des compétences du fait du turnover \& du niveau activité décroissant induisant des problèmes de qualité, délai et surcout

"#
  }
}