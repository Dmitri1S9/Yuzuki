pass1 <- read.csv("pass1.csv", stringsAsFactors=FALSE, na.strings="None")
pass2 <- read.csv("pass2.csv", stringsAsFactors=FALSE, na.strings="None")

FLAG_COLS <- c(
  "manipulative","honest","impulsive","secretive","self_sacrificing",
  "adaptable","loyal","empathetic","cruel","arrogant","competitive",
  "ruthless","is_strategist","has_humor",
  "is_physically_attractive","is_intimidating","is_muscular",
  "has_distinctive_feature","is_well_groomed",
  "goal_power","goal_love","goal_knowledge","goal_revenge",
  "goal_survival","goal_duty","goal_freedom","goal_recognition","goal_protection",
  "military","politics","science","art","education","crime","commerce",
  "has_magic","has_tragic_past","is_strong_willed","is_provocative",
  "is_loner","is_unstable","is_fanatical",
  "is_idealist","is_nihilist","is_pragmatist","is_hedonist",
  "is_machiavellian","is_revolutionary","is_fatalist",
  "has_physical_weakness","has_psychological_weakness"
)
RANK_COLS <- c(
  "combat_potential","intellect","authority_scope",
  "loyalty_command","social_impact","wealth"
)
ALL_COLS <- c(FLAG_COLS, RANK_COLS)

# ── Cohen's Kappa ─────────────────────────────────────────────────────────────
cohen_kappa <- function(r1, r2) {
  n <- length(r1)
  if (n < 2) return(NA_real_)
  lvls <- sort(unique(c(r1, r2)))
  tab  <- table(factor(r1, levels=lvls), factor(r2, levels=lvls))
  po   <- sum(diag(tab)) / n
  pe   <- sum(rowSums(tab) * colSums(tab)) / n^2
  if (abs(1 - pe) < 1e-10) return(NA_real_)
  (po - pe) / (1 - pe)
}

# ── Category derivations from score = tier*10 + within ────────────────────────

# 1. TIER: integer tier the character is in
cat_tier <- function(score) as.integer(floor(score / 10))

# 2. BUCKET: tier * 3 + position within tier (low/mid/high)
#    using normal CDF thresholds: pnorm(-1)≈0.159, pnorm(1)≈0.841
cat_bucket <- function(score) {
  tier   <- floor(score / 10)
  within <- score - tier * 10
  bucket <- ifelse(within < 0.159, 0L, ifelse(within < 0.841, 1L, 2L))
  as.integer(tier * 3 + bucket)
}

# 3. ORDER: global rank position → quartile (1-4)
cat_order <- function(scores) {
  r <- rank(scores, ties.method="average")
  as.integer(ceiling(r / length(r) * 4))
}