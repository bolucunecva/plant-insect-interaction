library(readr)
library(tidyr)
library(dplyr)

dat <- read_csv("plant_insect_dataset_lifestage_cleaned_with_plant_organ_normalized.csv", show_col_types = FALSE)


dat |>
  filter(!is.na(plant_organ)) |>
  distinct(plant_organ)-> plant_unique

dir.create("ontology", showWarnings = FALSE)

download.file(
  "https://purl.obolibrary.org/obo/po.obo",
  destfile = "ontology/po.obo"
)


library(ontologyIndex)

po <- get_ontology(
  "ontology/po.obo",
  propagate_relationships = c("is_a")
)


target_organs <- c(
  leaf   = "PO:0025034",
  root   = "PO:0009005",
  stem   = "PO:0009047",
  flower = "PO:0009046",
  fruit  = "PO:0009001",
  seed   = "PO:0009010",
  whole_plant = "PO:0000003"
)


#PO organ look up table

library(dplyr)
library(tidyr)

descendants <- lapply(target_organs, function(root_id) {
  get_descendants(po, root_id)
})

po_map <- tibble(
  po_id = unlist(descendants),
  organ = rep(names(descendants), lengths(descendants))
)

#Normalize raw strings
library(stringr)

normalize_text <- function(x) {
  x |>
    str_to_lower() |>
    str_replace_all("[^a-z0-9,/\\- ]", " ") |>
    str_replace_all("\\s+", " ") |>
    str_trim()
}

classify_substrate_multi <- function(x) {
  x <- stringr::str_to_lower(x)
  
  is_litter <- stringr::str_detect(
    x, "leaf litter|pine.?needle litter|needle litter|ground litter|litter layer|senescent.*litter|\\bstem litter\\b|\\blitter\\b"
  )
  
  is_deadwood <- stringr::str_detect(
    x, "dead ?wood|deadwood|\\blog\\b|\\blogs\\b|dead tree|snag|snags|stump|fallen logs?|dead trunk|dead twig|dead branch|dead branches|dead heart|dead hearts|stump|lying or stump|dead hearts? of sugarcane|dead hearts?\\b"
  )
  
  dplyr::case_when(
    is_litter & is_deadwood ~ "leaf_litter|deadwood",
    is_litter ~ "leaf_litter",
    is_deadwood ~ "deadwood",
    TRUE ~ NA_character_
  )
}


po_raw <- plant_unique |>
  mutate(
    plant_organ_norm = normalize_text(plant_organ),
    substrate = classify_substrate_multi(plant_organ_norm)
  )

#Tokenize multiple organs

po_tokens <- po_raw |>
  mutate(
    plant_organ_norm = str_replace_all(plant_organ_norm, "\\[|\\]|\\'", " "),  # remove ['...']
    plant_organ_norm = str_replace_all(plant_organ_norm, "\\(", " ("),         # spacing
    plant_organ_norm = str_replace_all(plant_organ_norm, "\\)", ") ")
  ) |>
  separate_rows(plant_organ_norm, sep = "\\s*(,|/|;|\\band\\b)\\s*") |>
  mutate(token = str_squish(plant_organ_norm)) |>
  filter(token != "")


library(dplyr)
library(tidyr)
library(stringr)
library(purrr)

# ---- (2) regex constants (named) ----

# simple concatenation helper (base R doesn’t have %+%)
`%+%` <- function(a, b) paste0(a, b)

#semantic overrides (biology-aware)
rx <- list(
  bud_any        = "\\bbuds?\\b",
  bud_struct     = "\\b(apical|lateral|axillary|terminal|dormant)\\b\\s*buds?\\b|\\b(apical|lateral|axillary|terminal|dormant)\\b",
  bud_flower     = "\\b(flowering|floral|flower|reproductive|staminate|square|raceme)\\b",
  bud_veg        = "\\bvegetative\\b",
  cone_any       = "\\bcones?\\b|\\bstrobil(us|i)\\b",
  domatia        = "\\bdomatia\\b",
  fruiting       = "\\b(apples|apple cores calyx exposed|berry|coffee berry|fruitlets|drupelet|drupes|pericarp|mesocarp|exocarp|occasionally exocarp|infructescences|syconium|fig|sycons|infructescences|seedpod|seedpods|seedpods siliques|silique|silicles|husk|husks|walnut husk|cherelles?)\\b",
  phloem         = "\\bphloem\\b",
  peel           = "\\b(peels?|rind|skin|rinde)\\b",
  root_context   = "\\b(tuber|root|bulb|corm)\\b",
  seed_context   = "\\b(achenes|acorns|embryo|radicle|coleoptile|embryonic axis|sori)\\b", #sori added bc functionally is seed-like
  treeplant      = "\\b(tree|trees|plant|plants|seedling|seedlings)\\b",
  exclude_whole  = "\\b(canopy|crown|trunk|branch|branches|twig|twigs|bark|wood|"
  %+% "leaf|leaves|needle|needles|root|roots|stem|stems|shoot|shoots|"
  %+% "bud|buds|flower|flowers|fruit|fruits|seed|seeds|litter|deadwood|"
  %+% "part|parts|aboveground|belowground|aerial|understory|vegetation)\\b"
)


# Whole-plant token detector (9)
is_wholeplant_token <- function(t) {
  t <- stringr::str_to_lower(t)
  
  # 1) explicit "whole plant/tree" patterns (optionally with parentheses)
  #    examples: "whole plant", "whole plant (alfalfa)", "whole tree habitat"
  if (stringr::str_detect(
    t,
    "^\\s*whole\\s+(plant|plants|tree|trees)\\b(\\s*\\([^)]*\\))?\\s*$|^\\s*whole\\s+(plant|plants|tree|trees)\\b"
  )) {
    # still exclude cases where "whole ..." is clearly followed by a specific organ/part
    if (!stringr::str_detect(
      t,
      "\\b(canopy|crown|trunk|branch(?:es)?|twig(?:s)?|bark|wood|log(?:s)?|snag(?:s)?|
         stump(?:s)?|bole(?:s)?|stem(?:s)?|shoot(?:s)?|leaf|leaves|needle(?:s)?|
         root(?:s)?|flower(?:s)?|fruit(?:s)?|seed(?:s)?|bud(?:s)?|
         litter|deadwood|part(?:s)?)\\b"
    )) {
      return(TRUE)
    }
  }
  
  # 2) must contain tree / plant somewhere
  if (!stringr::str_detect(t, "\\b(tree|trees|plant|plants)\\b")) {
    return(FALSE)
  }
  
  # 3) exclude explicit organs or parts
  if (stringr::str_detect(
    t,
    "\\b(canopy|crown|trunk|branch(?:es)?|twig(?:s)?|bark|wood|log(?:s)?|snag(?:s)?|
       stump(?:s)?|bole(?:s)?|stem(?:s)?|shoot(?:s)?|leaf|leaves|needle(?:s)?|
       root(?:s)?|flower(?:s)?|fruit(?:s)?|seed(?:s)?|bud(?:s)?|
       litter|deadwood|part(?:s)?|aboveground|belowground|aerial|
       understory|vegetation)\\b"
  )) {
    return(FALSE)
  }
  
  # 4) token must be JUST tree/plant OR end with it
  stringr::str_detect(
    t,
    "^\\s*(tree|trees|plant|plants)\\s*$|\\b(tree|trees|plant|plants)\\s*$"
  )
}


#non-plant classifier
classify_nonplant <- function(t) {
  t <- stringr::str_to_lower(t)
  
  dplyr::case_when(
    # insect/animal body parts or stages
    stringr::str_detect(t, "\\b(eye|leg|antennae|rostrum|cuticle|abdomen|chest|dorsum|flanks|wing|cloacal|under tail|neck|liver|body)\\b") ~ "nonplant_animal",
    
    # insect life stages / structures
    stringr::str_detect(t, "\\b(egg|eggs|larva|larval|aphids|aphid|larvae|pupa|pupae|cocoon|pupal case|galls?)\\b") ~ "nonplant_insect",
    
    # soils/water/ground/environment (not plant tissue)
    stringr::str_detect(t, "\\b(soil|ground|sand|riverbank|stream margin|wetland floor|water surface|waterlot|burrow|forest understory|understory vegetation|vegetation community|grassland|crop field|paddy field|rice paddies)\\b") ~ "nonplant_environment",
    
    # substrates / materials / products / lab stuff
    stringr::str_detect(t, "\\b(filter paper|wax comb|comb|nest material|sawdust|compost|substrate|casing layer|potting soil|timber|logs?|bolts|sticks|powder|flour|oil|essential oil|extract|latex)\\b") ~ "nonplant_material",
    
    # fungi etc.
    stringr::str_detect(t, "\\b(mycelium|sporophores|fungi|sclerotia)\\b") ~ "nonplant_fungi",
    
    TRUE ~ NA_character_
  )
}


#classify plant-related but not organ
classify_nonorgan_plantish <- function(t) {
  t <- stringr::str_to_lower(t)
  
  dplyr::case_when(
    stringr::str_detect(t, "\\b(unknown|unidentified|not found|not specified|unspecified|none|various)\\b") ~ "plant_unspecified",
    stringr::str_detect(t, "\\b(herb|herbs|herbaceous|grass|grasses|forb|forbs|shrub|shrubs)\\b") ~ "plant_type",
    stringr::str_detect(t, "\\b(breeding site|colonisation site|oviposition sites|larval feeding sites)\\b") ~ "plant_context",
    stringr::str_detect(t, "\\b(mature|immature|ripening|senescing|senescent|green|yellow|old|young|wounds?)\\b") ~ "plant_stage_or_condition",
    stringr::str_detect(t, "\\b(upper|lower|middle|top|basal|apical|outer margin)\\b") ~ "plant_position",
    TRUE ~ NA_character_
  )
}

#broad lexical hints
manual_map <- tibble::tribble(
  ~pattern, ~organ,
  
  # leaf-like
  "\\b(acicule|leaf|leaves|needle|needles|frond|fronds|leaflet|leaflets|canopy|foliage|petiole|cotyledons?|abaxial|adaxial|phyllode(s)?|lamina|blade|midrib(s)?|midvein(s)?|pinna|foliar|mesophyll|petiole(s)?|stipule(s)?|trifoliates|trichomes?|chlorenchyma|epidermis)\\b",
  "leaf",
  
  # root-like
  "\\b(root|roots|rhizome|tubers?|bulbs?|corms?|rootstock|rootlets?|potato|potatoes|cloves?)\\b",
  "root",
  
  # stem-like
  "\\b(hypocotyl|cambium|bole|boles|stems?|stalk|culm|shoots?|twig|twigs|branch|branches|trunk(s)?|wood|bark|cladodes?|vines?|haulm|xylem|protoxylem|internode(s)?|node(s)?|tiller(s)?|culm(s)?|rachis|peduncle|cane|pseudostem|burl|woody|cambium|sapwood|heartwood|tracheids|rays|resin canals?|stelar vascular bundle|vascular cylinder)\\b",
  "stem",
  
  # flower-like
  "\\b(floret|florets|spathe|flower|flowers|floral|inflorescences?|blossoms?|panicles?|spadix|spike|spikes|tassels?|catkins?)\\b",
  "flower",
  
  # flowers and inflorescences
  "\\b(flower|flowers|floral|bloom|blooms|inflorescence(s)?|flowerhead(s)?|capitulum|capitula|umbel(s)?|spike|spikes|spikelet(s)?|panicle(s)?|tassel(s)?|catkin(s)?|head flowering head|wheat head)\\b",
  "flower",
  
  # floral organs
  "\\b(calyx|calyces|corolla|petal(s)?|sepal(s)?|perianth|perigone|labellum)\\b",
  "flower",
  
  # reproductive structures
  "\\b(stamen(s)?|anther(s)?|filament(s)?|stigma|stigmata|style(s)?|ovary|ovaries|ovule(s)?)\\b",
  "flower",
  
  # pollination reproduction
  "\\b(pollen|pollinaria|nectar|nectaries)\\b",
  "flower",
  
  # vague reproductive terms
  "\\b(reproductive|reproductive organs|reproductive structures|generative|generative organs|generative parts)\\b",
  "flower",
  
  # fruit-like
  "\\b(fruit|fruits|pods?|berries|bolls?|capsules?|ears?|cobs?|copra|nuts?)\\b",
  "fruit",
  
  # seed-like
  "\\b(seed|seeds|grains?|kernels?|acorn|cones?|strobil(us|i)|scales?)\\b",
  "seed"
)

# Precompile regex (faster + clearer)
manual_rules <- manual_map |>
  mutate(re = regex(pattern, ignore_case = TRUE)) |>
  select(re, organ)

# Vector-friendly matching (no rowwise) (1)
match_organs <- function(token, manual_rules) {
  hits <- manual_rules$organ[map_lgl(manual_rules$re, ~ str_detect(token, .x))]
  unique(hits)
}

tokenise_organs <- function(x) {
  x |>
    str_replace_all("\\[|\\]|\\'", " ") |>
    str_replace_all("\\(", " (") |>
    str_replace_all("\\)", ") ") |>
    str_split("\\s*(,|/|;|\\band\\b)\\s*") |>
    map(str_squish) |>
    map(~ .x[.x != ""]) |>
    unlist(use.names = FALSE)
}

# Build tokens table cleanly
po_tokens <- po_raw |>
  mutate(tokens = map(plant_organ_norm, tokenise_organs)) |>
  unnest(tokens) |>
  transmute(plant_organ, plant_organ_norm, substrate, token = tokens) |>
  filter(token != "")


#priority logic and conflict resolution
apply_context_rules <- function(token, organs) {
  t <- str_to_lower(token)
  
  # ensure organs is a character vector
  organs <- organs[!is.na(organs)]
  if (length(organs) == 0) organs <- character()
  
  # 1) non-plant early exit
  np <- classify_nonplant(t)
  if (!is.na(np)) return(np)
  
  # 2) plant-ish but not an organ early exit
  po <- classify_nonorgan_plantish(t)
  if (!is.na(po)) return(po)
  
  # 3) whole plant early exit (9)
  if (is_wholeplant_token(t)) return("whole_plant")
  
  # 3.1) fruit related
  if (str_detect(t, rx$fruiting)) return("fruit")
  
  # 3.2) seed-related
  if (str_detect(t, rx$seed_context)) return("seed")
  
  # 4) hard overrides
  if (str_detect(t, rx$domatia)) return("leaf")
  if (str_detect(t, rx$cone_any)) return("seed")
  if (str_detect(t, "\\bcladodes?\\b")) return("stem")
  if (str_detect(t, "\\bvines?\\b|\\blianas?\\b")) return("stem")
  
  # 5) phloem disambiguation
  if (str_detect(t, rx$phloem)) {
    if (str_detect(t, "\\b(root|roots|rhizosphere)\\b")) return("root")
    if (str_detect(t, "\\b(leaf|leaves|midrib|midvein|petiole|foliar)\\b")) return("leaf")
    return("stem")  # default
  }
  
  # 6) peel/rind/skin disambiguation (root vs fruit)
  if (str_detect(t, rx$peel)) {
    if (str_detect(t, rx$root_context)) return("root")
    return("fruit")
  }
  
  # 7) bud rules
  if (str_detect(t, rx$bud_any)) {
    # structural/location buds => stem (your preference)
    if (str_detect(t, rx$bud_struct)) return("stem")
    
    # flowering/reproductive buds => flower
    if (str_detect(t, rx$bud_flower)) return("flower")
    
    # vegetative buds => leaf
    if (str_detect(t, rx$bud_veg)) return("leaf")
    
    # bud + needle/cone => leaf (you requested earlier)
    if (str_detect(t, "\\bneedle|needles\\b") || str_detect(t, rx$cone_any)) return("leaf")
    
    # default bud
    return("leaf")
  }
  
  # 8) keep manual matches if any, else unknown
  if (length(organs) > 0) return(unique(organs))
  "unknown"
}


valid_organs <- c("leaf","stem","flower","root","fruit","seed","whole_plant")

mk_class <- function(token_type, organ_class = NA_character_,
                     nonplant_class = NA_character_,
                     plantish_nonorgan_class = NA_character_,
                     why = NA_character_) {
  list(
    token_type = token_type,
    organ_class = organ_class,
    nonplant_class = nonplant_class,
    plantish_nonorgan_class = plantish_nonorgan_class,
    why = why
  )
}

classify_token <- function(token, organs_guess) {
  t <- stringr::str_to_lower(token)
  
  organs_guess <- organs_guess[!is.na(organs_guess)]
  if (length(organs_guess) == 0) organs_guess <- character()
  
  np <- classify_nonplant(t)
  if (!is.na(np)) return(mk_class("nonplant", nonplant_class = np, why = "nonplant"))
  
  po <- classify_nonorgan_plantish(t)
  if (!is.na(po)) return(mk_class("plantish_nonorgan", plantish_nonorgan_class = po, why = "plantish_nonorgan"))
  
  if (is_wholeplant_token(t)) return(mk_class("plant_organ", organ_class = "whole_plant", why = "wholeplant"))
  
  if (stringr::str_detect(t, rx$fruiting))     return(mk_class("plant_organ", "fruit", why = "fruiting_override"))
  if (stringr::str_detect(t, rx$seed_context)) return(mk_class("plant_organ", "seed",  why = "seed_override"))
  if (stringr::str_detect(t, rx$domatia))      return(mk_class("plant_organ", "leaf",  why = "domatia_override"))
  if (stringr::str_detect(t, rx$cone_any))     return(mk_class("plant_organ", "seed",  why = "cone_override"))
  if (stringr::str_detect(t, "\\bcladodes?\\b")) return(mk_class("plant_organ", "stem", why = "cladode_override"))
  if (stringr::str_detect(t, "\\bvines?\\b|\\blianas?\\b")) return(mk_class("plant_organ", "stem", why = "vine_override"))
  
  if (stringr::str_detect(t, rx$phloem)) {
    organ <- if (stringr::str_detect(t, "\\b(root|roots|rhizosphere)\\b")) "root"
    else if (stringr::str_detect(t, "\\b(leaf|leaves|midrib|midvein|petiole|foliar)\\b")) "leaf"
    else "stem"
    return(mk_class("plant_organ", organ, why = "phloem_rule"))
  }
  
  if (stringr::str_detect(t, rx$peel)) {
    organ <- if (stringr::str_detect(t, rx$root_context)) "root" else "fruit"
    return(mk_class("plant_organ", organ, why = "peel_rule"))
  }
  
  if (stringr::str_detect(t, rx$bud_any)) {
    organ <- if (stringr::str_detect(t, rx$bud_struct)) "stem"
    else if (stringr::str_detect(t, rx$bud_flower)) "flower"
    else if (stringr::str_detect(t, rx$bud_veg)) "leaf"
    else if (stringr::str_detect(t, "\\bneedle|needles\\b") || stringr::str_detect(t, rx$cone_any)) "leaf"
    else "leaf"
    return(mk_class("plant_organ", organ, why = "bud_rule"))
  }
  
  if (length(organs_guess) > 0) {
    return(mk_class("plant_organ", organs_guess[1], why = "manual_guess"))
  }
  
  mk_class("unknown", why = "unknown")
}


po_tokens2 <- po_tokens |>
  mutate(organs_guess = map(token, match_organs, manual_rules = manual_rules))

po_tokens3 <- po_tokens2 |>
  mutate(class = map2(token, organs_guess, classify_token)) |>
  tidyr::unnest_wider(class) |>
  mutate(
    # confidence: only meaningful for plant organ calls
    confidence = case_when(
      token_type == "plant_organ" & organ_class %in% valid_organs ~ "high",
      token_type == "plant_organ" ~ "low",
      TRUE ~ "n/a"
    )
  )


po_tokens3_fix <- po_tokens3 |>
  mutate(organs = map(organ_class, ~ if (length(.x) == 0) "unknown" else .x))

po_tokens4 <- po_tokens3_fix |>
  mutate(
    confidence = map_chr(organs, ~ if (all(.x %in% valid_organs)) "high" else "low")
  )


final_semantic <- po_tokens3 |>
  group_by(plant_organ) |>
  summarise(
    organ = paste(sort(unique(na.omit(organ_class))), collapse = "|") |> dplyr::na_if(""),
    substrate = paste(sort(unique(na.omit(substrate))), collapse = "|") |> dplyr::na_if(""),
    nonplant = paste(sort(unique(na.omit(nonplant_class))), collapse = "|") |> dplyr::na_if(""),
    plantish_nonorgan = paste(sort(unique(na.omit(plantish_nonorgan_class))), collapse = "|") |> dplyr::na_if(""),
    .groups = "drop"
  )


#final_semantic %>% filter(!is.na(substrate) | !is.na(nonplant) | !is.na(plantish_nonorgan) & is.na(organ))-> qa1

#final_semantic %>% filter(is.na(substrate) & is.na(nonplant) & is.na(plantish_nonorgan) & is.na(organ)) %>%
#  distinct(plant_organ)-> qa2

#final_semantic %>% filter(is.na(substrate) & is.na(nonplant) & is.na(plantish_nonorgan) & is.na(organ)) -> qa2i

write_csv(final_semantic, "plant_insect_dataset_lifestage_cleaned_with_plant_organ_normalized_review.csv")
                          
