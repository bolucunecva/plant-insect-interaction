# Plan-Insect Interaction Dataset

This repository contains data and code for building a plant-insect interaction dataset from scientific literature, external biodiversity APIs, and post-processing pipelines. This dataset is configured to be indexed by Global Biotic Interactions (GloBI, https://globalbioticinteractions.org).

The project combines:
- Literature retrieval (OpenAlex and Web of Science exports)
- PDF collection and filtering
- Structured information extraction from article text
- Taxonomy normalisation (iNaturalist, GBIF, TNRS)
- Geographic normalisation and enrichment

 ## Data
Data can be found in the `/data` directory.

### Dataset Detail

This is a dataset for ecological analysis.
Columns: 
- ID: unique iid of publication (DOI)
- insect_family
- insect_taxon
- plant_family
- plant_taxon
- plant_organ
- geographic_location
- latitude
- longitude
- insect_lifestage_when_on_host: normalised via INaturalist of GBIF
- insect_taxon_canonical_name: normalised via INaturalist of GBIF
- insect_taxon_rank: normalised via INaturalist of GBIF
- insect_taxon_hierarchy: normalised via INaturalist of GBIF
- plant_taxon_name_matched: normalised via TNRS
- plant_taxon_accepted_family: normalised via TNRS



## Repository Goals

- Build a reproducible dataset of plant-insect interaction records.
- Enrich raw extraction outputs with taxonomic and geographic metadata.
- Produce cleaned datasets for downstream analysis and integration (for example, GloBI-style indexing workflows).
- 
This repository provides a sample dataset that contains plant-insect interactions.

 




