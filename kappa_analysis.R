args <- commandArgs(trailingOnly=TRUE)
slug <- if (length(args) >= 1) args[1] else "classroom_of_the_elite_year_1"

pass1 <- read.csv(sprintf("run/pass1_%s.csv", slug), stringsAsFactors=FALSE, na.strings="None", check.names=FALSE)
pass2 <- read.csv(sprintf("run/pass2_%s.csv", slug), stringsAsFactors=FALSE, na.strings="None", check.names=FALSE)
pass3 <- read.csv(sprintf("run/pass3_%s.csv", slug), stringsAsFactors=FALSE, na.strings="None", check.names=FALSE)

RANK_COLS <- c(
  "combat_potential","intellect","authority_scope",
  "loyalty_command","social_impact","wealth"
)
ALL_COLS  <- setdiff(names(pass1), "entity")
FLAG_COLS <- setdiff(ALL_COLS, RANK_COLS)

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
cat_tier <- function(score) as.integer(floor(score / 10))

cat_bucket <- function(score) {
  tier   <- floor(score / 10)
  within <- score - tier * 10
  bucket <- ifelse(within < 0.159, 0L, ifelse(within < 0.841, 1L, 2L))
  as.integer(tier * 3 + bucket)
}

# ── Kappa for one column over one pair of passes ──────────────────────────────
pair_kappa <- function(col, dfa, dfb, cat_fn) {
  sa <- as.numeric(dfa[[col]]); sb <- as.numeric(dfb[[col]])
  mask <- !is.na(sa) & !is.na(sb)
  if (sum(mask) < 2) return(NA_real_)
  cohen_kappa(cat_fn(sa[mask]), cat_fn(sb[mask]))
}

# ── kappa_12 and kappa_min over 1x2, 1x3, 2x3 ─────────────────────────────────
# kappa_min = worst of the three pairwise passes, not the median: a parameter
# only counts as reliable if EVERY pair of independent passes agrees, not just
# most of them. This is the harsher, start-here bar.
safe_min <- function(x) {
  x <- x[!is.na(x)]
  if (length(x) == 0) return(NA_real_)
  min(x)
}
run_kappa <- function(cols) {
  out <- data.frame()
  for (col in cols) {
    k <- list()
    for (nm in c("tier","bucket")) {
      fn <- if (nm == "tier") cat_tier else cat_bucket
      k12 <- pair_kappa(col, pass1, pass2, fn)
      k13 <- pair_kappa(col, pass1, pass3, fn)
      k23 <- pair_kappa(col, pass2, pass3, fn)
      k[[nm]] <- list(k12=k12, min=safe_min(c(k12,k13,k23)))
    }
    sa <- as.numeric(pass1[[col]])
    out <- rbind(out, data.frame(
      col          = col,
      tier_12      = round(k$tier$k12, 3),
      tier_min     = round(k$tier$min, 3),
      bucket_min   = round(k$bucket$min, 3),
      n_unknown    = sum(is.na(sa)),
      stringsAsFactors = FALSE
    ))
  }
  out
}

# ── Filter by kappa_min: tier (model's own tiers, real pass vs real pass)
# gates, bucket (finer within-tier position) splits the verdict. The old
# order gate (quartile-of-roster-position, ignoring the model's own tiers)
# was removed — same tie-breaks it was meant to catch already show up as
# tier disagreement, without the artifact of forcing exactly 4 equal-size
# groups regardless of how many tiers a pass actually used.
verdict <- function(tier_min, bucket_min) {
  if (is.na(tier_min) || tier_min < 0.5) return("DROP")
  if (!is.na(bucket_min) && bucket_min >= 0.5) return("continuous-valid (z-score)")
  "categorical-valid (tier only)"
}

report <- function(title, res) {
  res$verdict <- mapply(verdict, res$tier_min, res$bucket_min)
  res <- res[order(res$tier_min, na.last=TRUE), ]
  cat(sprintf("\n══ %s ══\n", title))
  print(res, row.names=FALSE)
  cat(sprintf("\nmean kappa_min — tier: %.3f  bucket: %.3f\n",
              mean(res$tier_min, na.rm=TRUE),
              mean(res$bucket_min, na.rm=TRUE)))
  cat(sprintf("verdicts: DROP=%d  continuous=%d  categorical=%d\n",
              sum(res$verdict == "DROP"),
              sum(res$verdict == "continuous-valid (z-score)"),
              sum(res$verdict == "categorical-valid (tier only)")))
  res
}

rank_res <- report("RANKS", run_kappa(RANK_COLS))
flag_res <- report("FLAGS", run_kappa(FLAG_COLS))

out_file <- sprintf("run/kappa_verdicts_%s.csv", slug)
write.csv(rbind(rank_res, flag_res), out_file, row.names=FALSE)
cat(sprintf("\nwrote %s\n", out_file))
