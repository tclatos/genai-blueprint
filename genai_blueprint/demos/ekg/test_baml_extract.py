"""Test script to demonstrate BAML-based structured extraction.

This script provides a way to test the BAML ExtractRainbow function with sample
markdown content to verify that the structured extraction is working correctly.
"""

import asyncio

from genai_blueprint.demos.ekg.cli_commands.commands_baml import BamlStructuredProcessor
from loguru import logger

from genai_blueprint.demos.ekg.baml_client import b as baml_sync_client
from genai_blueprint.demos.ekg.baml_client.async_client import b as baml_async_client

# Sample rainbow document content from the BAML test
SAMPLE_RAINBOW_CONTENT = """# Solution Review Slides

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
- Problèmes à traiter sur sujets non maitrisés ou un périmètre trop grand du fait de la transition minimum sur Venus/VIP \\& intermédiaire sur THEIA/MUSCATE induisant des problèmes de qualité, délai et surcout
- Difficultés à maintenir des compétences du fait du turnover \\& du niveau activité décroissant induisant des problèmes de qualité, délai et surcout
"""


def test_sync_client():
    """Test the synchronous BAML client."""
    logger.info("Testing synchronous BAML client...")

    try:
        result = baml_sync_client.ExtractRainbow(rainbow_file=SAMPLE_RAINBOW_CONTENT)
        logger.success(f"Sync client result: {result.name}")
        logger.info(f"Opportunity ID: {result.opportunity_id}")
        logger.info(f"Customer: {result.customer}")
        logger.info(f"TCV: {result.financials.tcv if result.financials else 'N/A'}")
        return result
    except Exception as e:
        logger.error(f"Sync client failed: {e}")
        return None


async def test_async_client():
    """Test the asynchronous BAML client."""
    logger.info("Testing asynchronous BAML client...")

    try:
        result = await baml_async_client.ExtractRainbow(rainbow_file=SAMPLE_RAINBOW_CONTENT)
        logger.success(f"Async client result: {result.name}")
        logger.info(f"Opportunity ID: {result.opportunity_id}")
        logger.info(f"Customer: {result.customer}")
        logger.info(f"TCV: {result.financials.tcv if result.financials else 'N/A'}")
        return result
    except Exception as e:
        logger.error(f"Async client failed: {e}")
        return None


async def test_processor():
    """Test the BamlStructuredProcessor."""
    logger.info("Testing BamlStructuredProcessor...")

    processor = BamlStructuredProcessor(kvstore_id=None)  # Skip KV store for testing

    try:
        result = processor.analyze_document("test_doc", SAMPLE_RAINBOW_CONTENT)
        logger.success(f"Processor result: {result.name}")
        logger.info(f"Opportunity ID: {result.opportunity_id}")
        logger.info(f"Customer: {result.customer}")
        logger.info(f"TCV: {result.financials.tcv if result.financials else 'N/A'}")
        return result
    except Exception as e:
        logger.error(f"Processor failed: {e}")
        return None


async def main():
    """Run all tests."""
    logger.info("Starting BAML extraction tests...")

    # Test sync client
    sync_result = test_sync_client()

    # Test async client
    async_result = await test_async_client()

    # Test processor
    processor_result = await test_processor()

    # Summary
    logger.info("Test Summary:")
    logger.info(f"Sync client: {'✓' if sync_result else '✗'}")
    logger.info(f"Async client: {'✓' if async_result else '✗'}")
    logger.info(f"Processor: {'✓' if processor_result else '✗'}")

    if sync_result:
        logger.info(f"\nExtracted project: {sync_result.name}")
        logger.info(f"Teams: {len(sync_result.team)} people")
        logger.info(f"Risks: {len(sync_result.risks)} identified")


if __name__ == "__main__":
    asyncio.run(main())
