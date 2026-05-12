setwd("C:/Users/dmitr/Desktop/Yuzuki")

pass1_raw <- read.csv("pass1.csv", stringsAsFactors = FALSE, na.strings = "None")
pass2_raw <- read.csv("pass2.csv", stringsAsFactors = FALSE, na.strings = "None")

# rows: characters + T0 + T1; entity column = name
# flag columns: all except "entity"

flags <- setdiff(names(pass1_raw), "entity")
chars <- pass1_raw$entity[!(pass1_raw$entity %in% c("T0", "T1"))]

# ── category derivation ───────────────────────────────────────────────────────
# position < T0 pos  ->  0 (no trait)
# T0 < position < T1 ->  1 (borderline)
# position > T1 pos  ->  2 (has trait)

get_cats <- function(df, flag) {
  t0 <- as.integer(df[df$entity == "T0", flag])
  t1 <- as.integer(df[df$entity == "T1", flag])
  vals <- as.integer(df[df$entity %in% chars, flag])
  ifelse(is.na(vals), NA_integer_,
    ifelse(vals < t0, 0L,
      ifelse(vals < t1, 1L, 2L)))
}

# ── Cohen's Kappa (base R) ────────────────────────────────────────────────────

cohen_kappa <- function(r1, r2) {
  n <- length(r1)
  if (n < 2) return(NA_real_)
  tab <- table(factor(r1, levels = 0:2), factor(r2, levels = 0:2))
  po  <- sum(diag(tab)) / n
  pe  <- sum(rowSums(tab) * colSums(tab)) / n^2
  if (abs(1 - pe) < 1e-10) return(NA_real_)
  (po - pe) / (1 - pe)
}

# ── per-flag kappa ────────────────────────────────────────────────────────────

results <- data.frame(flag=character(), kappa=numeric(),
                      n_rated=integer(), n_unknown=integer(),
                      stringsAsFactors=FALSE)

for (flag in flags) {
  r1   <- get_cats(pass1_raw, flag)
  r2   <- get_cats(pass2_raw, flag)
  mask <- !is.na(r1) & !is.na(r2)
  k    <- cohen_kappa(r1[mask], r2[mask])
  results <- rbind(results, data.frame(
    flag=flag, kappa=round(k,3),
    n_rated=sum(mask), n_unknown=sum(!mask),
    stringsAsFactors=FALSE))
}

results$stable <- ifelse(is.na(results$kappa), NA, results$kappa > 0.6)
results <- results[order(results$kappa, na.last=TRUE), ]

cat("\n── Cohen's Kappa per flag (sorted) ─────────────────────────────────\n")
print(results, row.names=FALSE)

cat("\n── Summary ─────────────────────────────────────────────────────────\n")
cat(sprintf("Stable   (kappa > 0.6): %d\n", sum(results$stable==TRUE,  na.rm=TRUE)))
cat(sprintf("Unstable (kappa < 0.6): %d\n", sum(results$stable==FALSE, na.rm=TRUE)))
cat(sprintf("NA:                     %d\n", sum(is.na(results$kappa))))
cat(sprintf("Mean kappa:             %.3f\n", mean(results$kappa, na.rm=TRUE)))

# ── pooled kappa ──────────────────────────────────────────────────────────────

all_r1 <- integer(0); all_r2 <- integer(0)
for (flag in flags) {
  r1 <- get_cats(pass1_raw, flag); r2 <- get_cats(pass2_raw, flag)
  mask <- !is.na(r1) & !is.na(r2)
  all_r1 <- c(all_r1, r1[mask]); all_r2 <- c(all_r2, r2[mask])
}
k_all <- cohen_kappa(all_r1, all_r2)
cat(sprintf("\nPooled kappa (all flags): %.3f  -> %s\n", k_all,
    ifelse(is.na(k_all), "NA",
           ifelse(k_all > 0.6, "STABLE — can proceed", "UNSTABLE — fix prompts"))))
