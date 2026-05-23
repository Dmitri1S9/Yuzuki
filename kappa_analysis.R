setwd("C:/Users/dmitr/Desktop/Yuzuki")

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

# ── Per-column kappa table ────────────────────────────────────────────────────
run_kappa <- function(cols, df1, df2) {
  results <- data.frame(
    col=character(), kappa_tier=numeric(), kappa_bucket=numeric(),
    kappa_order=numeric(), n_rated=integer(), n_unknown=integer(),
    stringsAsFactors=FALSE
  )
  for (col in cols) {
    s1 <- as.numeric(df1[[col]])
    s2 <- as.numeric(df2[[col]])
    mask <- !is.na(s1) & !is.na(s2)
    n_rated   <- sum(mask)
    n_unknown <- sum(!mask)
    if (n_rated < 2) {
      results <- rbind(results, data.frame(
        col=col, kappa_tier=NA, kappa_bucket=NA, kappa_order=NA,
        n_rated=n_rated, n_unknown=n_unknown, stringsAsFactors=FALSE))
      next
    }
    k_tier   <- cohen_kappa(cat_tier(s1[mask]),   cat_tier(s2[mask]))
    k_bucket <- cohen_kappa(cat_bucket(s1[mask]), cat_bucket(s2[mask]))
    # order kappa: compute rank within each pass separately
    k_order  <- cohen_kappa(cat_order(s1[mask]),  cat_order(s2[mask]))
    results <- rbind(results, data.frame(
      col=col,
      kappa_tier=round(k_tier,3), kappa_bucket=round(k_bucket,3),
      kappa_order=round(k_order,3),
      n_rated=n_rated, n_unknown=n_unknown, stringsAsFactors=FALSE))
  }
  results[order(results$kappa_tier, na.last=TRUE), ]
}

flag_res <- run_kappa(FLAG_COLS, pass1, pass2)
rank_res <- run_kappa(RANK_COLS, pass1, pass2)

# ── Output ────────────────────────────────────────────────────────────────────
print_section <- function(title, res) {
  cat(sprintf("\n══ %s ══\n", title))
  print(res, row.names=FALSE)
  cat(sprintf(
    "\nMean kappa — tier: %.3f  |  bucket: %.3f  |  order: %.3f\n",
    mean(res$kappa_tier,   na.rm=TRUE),
    mean(res$kappa_bucket, na.rm=TRUE),
    mean(res$kappa_order,  na.rm=TRUE)
  ))
}

print_section("FLAGS", flag_res)
print_section("RANKS", rank_res)

# ── Pooled kappas ─────────────────────────────────────────────────────────────
pool <- function(cols, cat_fn, df1, df2) {
  all1 <- integer(0); all2 <- integer(0)
  for (col in cols) {
    s1 <- as.numeric(df1[[col]]); s2 <- as.numeric(df2[[col]])
    mask <- !is.na(s1) & !is.na(s2)
    all1 <- c(all1, cat_fn(s1[mask])); all2 <- c(all2, cat_fn(s2[mask]))
  }
  cohen_kappa(all1, all2)
}

cat("\n══ POOLED ══\n")
for (label in c("tier","bucket","order")) {
  fn <- get(paste0("cat_", label))
  kf <- pool(FLAG_COLS, fn, pass1, pass2)
  kr <- pool(RANK_COLS, fn, pass1, pass2)
  cat(sprintf("%-8s  flags: %.3f %-22s  ranks: %.3f %s\n",
    label,
    kf, ifelse(is.na(kf),"(NA)", ifelse(kf>0.6,"[STABLE]","[UNSTABLE]")),
    kr, ifelse(is.na(kr),"(NA)", ifelse(kr>0.6,"[STABLE]","[UNSTABLE]"))))
}
