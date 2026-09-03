# LoRA Inventory — Gender Focus Classification

**Updated:** 2026-09-03
**Source:** Thunder box `/home/ubuntu/ComfyUI/models/loras/` (verified on disk, >1KB)
**Related session ref:** Abc342342 (H3/Civitai LoRA sourcing sweep)

Legend: ⚦ male-focused · ♀ female-focused · ⚧ trans-focused · ♥ couples/neutral

---

## ⚦ MALE-FOCUSED

### Anatomy / Penis
| File | Lane | Notes |
|---|---|---|
| `Male_Anatomy-v2.02-ep4.safetensors` | H3 | Diogod's H3 male anatomy (ass, penis, testicles, glans). WINNER for male H3 video. |
| `h3/Male_Anatomy-v2.02-ep4.safetensors` | H3 (subdir copy) | Same as above. |
| `Male_Nude_and_Genital_Anatomy_for_Flux_1_Dev.safetensors` | FLUX.1-dev | FLUX male nude/genital anatomy. **Do NOT use on Klein 4B/9B** — architecture mismatch → deformed junk. |
| `PENISLORA_WAN22_5B_e349.safetensors` | Wan 2.2 5B | Penis LoRA for the 5B Wan model. |
| `penislora22-high.safetensors` / `penislora22-low.safetensors` | Wan 2.2 14B | Penis LoRA high/low pair (bredbutterlog). Use high+low together. |
| `wan-erect-penis.safetensors` | Wan 2.2 | Erect penis focus. |
| `flux.2-klein-9b-penis-coachbate-v2.safetensors` | Klein 9B | CoachBate's paid penis LoRA for Klein 9B (632MB). |
| `Klein9BGeneralPenis-v1-5BETA.safetensors` | Klein 9B | General penis LoRA, free. |
| `KleinAnatomy_Male.safetensors` | Klein 9B | Klein male anatomy (free). |
| `Klein_Anatomy.safetensors` | Klein 9B | Klein anatomy (free, revamped zip extracted variant). |
| `MalePenis_Klein9B_v0.2.safetensors` | Klein 9B | Male penis v0.2 (free). |
| `h3/PLORA_H3_V2-step00006300.safetensors` | H3 | H3 penis LoRA. |
| `h3/Mini_Dick_Fix_V1.safetensors` | H3 | Mini dick fix / penis helper (T2V). |
| `h3/MiniMax-H3_uncut_penis_coachbate_v2_10000.safetensors` | H3 | CoachBate uncut penis (paid, downloaded). |
| `h3/MiniMax-H3-Ref2V_hyper_penis_coachbate_v1.safetensors` | H3 Ref2V | CoachBate hyper-penis / arousal (paid, downloaded). |
| `h3/Flux_Male_Ass_v5.safetensors` | H3 | Male ass view. |

### Male Acts / Content
| File | Lane | Notes |
|---|---|---|
| `bbc-blowjob.safetensors` | Wan | BBC blowjob — male receiver. |
| `bbc-ride.safetensors` | Wan | BBC ride — male-centered. |
| `male-masturbation.safetensors` | Wan | Male masturbation. |
| `igoon-handjob-high/low.safetensors` | Wan | Handjob (male receiver). |
| `igoon-handed-high/low.safetensors` | Wan | Handed / hand-focused (male receiver). |
| `wan22-cumshot-aesthetics-low.safetensors` | Wan | Cumshot aesthetics — male producer. |
| `gay_anal_sex-i2v-High_noise.safetensors` | Wan | Gay anal — male-male. |

---

## ♀ FEMALE-FOCUSED

### Anatomy / Body
| File | Lane | Notes |
|---|---|---|
| `SEXGOD_ImprovedNudity_Klein9b_v4.safetensors` | Klein 9B | **Female nudity helper** — gave "man with pussy" on male subjects. Female lane only! |
| `SEXGOD_CouplesNudity_Klein9b_v2.safetensors` | Klein 9B | Couples nudity (female emphasis). |
| `SexGod_Doggystyle_Klein9b_v1.safetensors` | Klein 9B | Doggystyle — female receiving. |
| `SEXGOD_Blowjobs_Klein9b_v1.safetensors` | Klein 9B | Blowjob — female performer. |
| `shexyo_style_klein9b.safetensors` | Klein 9B | Shexyo female style. |
| `flatchested-high/low.safetensors` | Wan | Flat-chested female body variant. |
| `genitals-helper.safetensors` / `genitals_helper_v1.0_e219.safetensors` | Wan | Female genitals helper (definitelynotadog). |
| `bodyshots-high/low.safetensors` | Wan | Body shots (female-focused framing). |
| `ebony-body.safetensors` | Wan | Ebony female body. |
| `js_wan_schoolgirl.safetensors` | Wan | Schoolgirl — female. |
| `wan2.2_ass_slider_v1_low_noise.safetensors` | Wan | Ass slider (female). |
| `h3/breastplayjiggle_h3_v2.safetensors` | H3 | Breast play & jiggle. |
| `h3/ass_jiggle_H3_i2v_v1.0.safetensors` | H3 | Ass jiggle (typically female). |

### Female Acts / Content
| File | Lane | Notes |
|---|---|---|
| `fingering_i2v_e248.safetensors` | Wan | Fingering. |
| `handpanties-high/low.safetensors` | Wan | Hand in panties. |
| `wan-deepthroat.safetensors` | Wan | Deepthroat — female performer. |
| `orgasm-high/low.safetensors` | Wan | Orgasm (female emphasis). |

---

## ⚧ TRANSGENDER-FOCUSED

| File | Lane | Notes |
|---|---|---|
| `futaTF-high.safetensors` / `futaTF-low.safetensors` | Wan 2.2 | Futanari transformation high/low pair — trans woman (female body + penis). |
| `wan22_i2v_futa_cowgirl_high_noise.safetensors` | Wan 2.2 | Futa cowgirl (trans female). |
| `h3/MiniMax-H3-Ref2V_hyper_penis_coachbate_v1.safetensors` | H3 Ref2V | Hyper-penis — usable for trans-male / hyper scenarios. |

*Note: No dedicated trans-male (FTM) LoRA found on the box yet. Futanari lane covers trans-woman. For trans-male we'd train custom or stack male anatomy on female body.*

---

## ♥ COUPLES / NEUTRAL / GENERAL

| File | Lane | Notes |
|---|---|---|
| `undress-all.safetensors` | Wan | "Change clothes to nothing" — **all genders** (Reddit-confirmed). |
| `nsfw22-high/low.safetensors` | Wan | General NSFW enhancement. |
| `wan-french-kissing-tongue.safetensors` | Wan | French kissing. |
| `wan22-frenchkiss-high/low.safetensors` | Wan | French kiss pairs. |
| `igoon-missionary-high/low.safetensors` | Wan | Missionary — couples. |
| `spanking_for_wan_v1_e128.safetensors` | Wan | Spanking — general. |
| `cumrag_sd15.safetensors` | SD1.5 | Cum/stain textures (model-specific, not Wan). |
| `ebony-face.safetensors` | Wan | Ebony face identity (gender-neutral subject). |
| `Wan2.2-I2V-High-MysticXXX.safetensors` | Wan | Mystic XXX — general NSFW style. |
| `KLEIN-Unchained-V2.safetensors` | Klein 9B | Unchained XXX — general NSFW style. |
| `h3/MysticXXX_MMH3-V4.safetensors` | H3 | Mystic XXX — general NSFW style. |
| `h3/NaughtyTimes_pruned_r256_v2.safetensors` | H3 | NaughtyTimes — general NSFW style (SexGod). |
| `h3/h3-realism-people-t2v-i2v-r2v.safetensors` | H3 | Realism people — general. |
| `h3/h3_Better_NSFW_Motion_V1.safetensors` | H3 | Better NSFW motion — general. |
| `h3/AfterMidnight_ref2va_h3_sexytime_rank64-v1.2.safetensors` | H3 | AfterMidnight sexytime (SexGod ref2va) — general motion/style. |
| `h3/AfterMidnight_ref2va_h3_softer_rank64_v1.safetensors` | H3 | AfterMidnight softer — general style. |
| `h3/VBVR_H3_attn_only.safetensors` | H3 | VBVR reasoning — general motion. |
| `h3/riding_pose_H3_i2v_v1.0.safetensors` | H3 | Riding pose — couples/female-on-top. |

---

## ⚡ SPEED / UTILITY (not gender-specific)

| File | Lane | Notes |
|---|---|---|
| `Wan2.2-Lightning_I2V-A14B-4steps-lora_HIGH/LOW_fp16.safetensors` | Wan | Lightning speed 4-step. |
| `lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank256_bf16.safetensors` | Wan | CFG-step-distill (YAW recipe, rank 256). |
| `minimax_h3_fl2v_lightx2v_turbo_4step/8step...` | H3 | H3 Turbo speed LoRAs. |
| `minimax_h3_ref2v_lightx2v_turbo_4step...` | H3 | H3 Ref2V Turbo. |

---

## ⚠️ KNOWN PITFALLS

1. **SEXGOD_ImprovedNudity is FEMALE.** It put a vulva on a male subject when stacked on a male prompt. Use ONLY for female subjects.
2. **Male_Nude_and_Genital_Anatomy_for_Flux_1_Dev is FLUX.1-dev-specific.** Loading it on Klein 4B/9B produced the "flesh blobs on waistband" artifacts.
3. **CoachBate Early Access:** Some CoachBate LoRAs still 99-byte-stub (Early Access / Buzz-gated) — check before relying.
4. **Klein 9B needs `qwen_3_8b_fp8mixed` text encoder**, NOT the 4B one (shape mismatch 512 vs 768).
5. **undress-all is gender-neutral but weak on male anatomy** — pair with a penis LoRA for males.
