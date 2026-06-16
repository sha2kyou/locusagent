import type { AppConfigUpdate } from "@/api/types";

export const AUXILIARY_MODEL_FIELD_DEFS = [
  { key: "auxiliary_vision_model" as const, labelKey: "settings.models.auxiliary.fields.vision.label", hintKey: "settings.models.auxiliary.fields.vision.hint" },
  { key: "auxiliary_web_extract_model" as const, labelKey: "settings.models.auxiliary.fields.webExtract.label", hintKey: "settings.models.auxiliary.fields.webExtract.hint" },
  { key: "auxiliary_compression_model" as const, labelKey: "settings.models.auxiliary.fields.compression.label", hintKey: "settings.models.auxiliary.fields.compression.hint" },
  { key: "auxiliary_title_generation_model" as const, labelKey: "settings.models.auxiliary.fields.titleGeneration.label", hintKey: "settings.models.auxiliary.fields.titleGeneration.hint" },
  { key: "auxiliary_approval_model" as const, labelKey: "settings.models.auxiliary.fields.approval.label", hintKey: "settings.models.auxiliary.fields.approval.hint" },
  { key: "auxiliary_curator_model" as const, labelKey: "settings.models.auxiliary.fields.curator.label", hintKey: "settings.models.auxiliary.fields.curator.hint" },
  { key: "auxiliary_skill_reflect_model" as const, labelKey: "settings.models.auxiliary.fields.skillReflect.label", hintKey: "settings.models.auxiliary.fields.skillReflect.hint" },
] satisfies ReadonlyArray<{
  key: keyof Pick<
    AppConfigUpdate,
    | "auxiliary_vision_model"
    | "auxiliary_web_extract_model"
    | "auxiliary_compression_model"
    | "auxiliary_title_generation_model"
    | "auxiliary_approval_model"
    | "auxiliary_curator_model"
    | "auxiliary_skill_reflect_model"
  >;
  labelKey: string;
  hintKey: string;
}>;

/** @deprecated use AUXILIARY_MODEL_FIELD_DEFS */
export const AUXILIARY_MODEL_FIELDS = AUXILIARY_MODEL_FIELD_DEFS;

export type AuxiliaryModelValues = Record<(typeof AUXILIARY_MODEL_FIELD_DEFS)[number]["key"], string>;

export const emptyAuxiliaryModels = Object.fromEntries(
  AUXILIARY_MODEL_FIELD_DEFS.map(({ key }) => [key, ""]),
) as AuxiliaryModelValues;

export function auxiliaryModelsFromConfig(llm: {
  auxiliary_vision_model?: string;
  auxiliary_web_extract_model?: string;
  auxiliary_compression_model?: string;
  auxiliary_title_generation_model?: string;
  auxiliary_approval_model?: string;
  auxiliary_curator_model?: string;
  auxiliary_skill_reflect_model?: string;
}): AuxiliaryModelValues {
  return Object.fromEntries(
    AUXILIARY_MODEL_FIELD_DEFS.map(({ key }) => [key, llm[key] ?? ""]),
  ) as AuxiliaryModelValues;
}

export function hasAuxiliaryModels(values: AuxiliaryModelValues): boolean {
  return Object.values(values).some((v) => v.trim());
}
