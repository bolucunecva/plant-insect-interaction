## Prerequisites

- Python 3.9+
- R (for postprocessing scripts)

### Python Dependencies

Install required Python packages:

```bash
pip install pandas rapidfuzz cachetools requests
```

### R Dependencies

The postprocessing scripts may require additional R packages. Install them in R/RStudio as needed.

## Postprocessing

Run the following scripts in order:

```bash
python postprocessing_insect_taxon.py
python postprocessing_plant_taxon.py
Rscript postprocessing_plant_organ.r
```

**Data flow:** 
- `postprocessing_plant_taxon.py` takes the output of `postprocessing_insect_taxon.py` as input
- `postprocessing_plant_organ.r` takes the output of `postprocessing_plant_taxon.py` as input
