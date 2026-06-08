import type { AppConfig, AppConfigUpdate } from "@/api/types";

export const AUXILIARY_MODEL_FIELDS = [
  {
    key: "auxiliary_vision_model" as const,
    label: "Vision 模型",
    hint: "图片理解；留空则使用主模型",
  },
  {
    key: "auxiliary_web_extract_model" as const,
    label: "网页提取模型",
    hint: "网页内容结构化提取；留空则使用主模型",
  },
  {
    key: "auxiliary_compression_model" as const,
    label: "上下文压缩模型",
    hint: "长对话上下文合并；留空则使用主模型",
  },
  {
    key: "auxiliary_title_generation_model" as const,
    label: "标题生成模型",
    hint: "会话标题自动生成；留空则使用主模型",
  },
  {
    key: "auxiliary_approval_model" as const,
    label: "安全检查模型",
    hint: "敏感操作审批；留空则使用主模型",
  },
  {
    key: "auxiliary_curator_model" as const,
    label: "记忆策展模型",
    hint: "长期记忆整理；留空则使用主模型",
  },
  {
    key: "auxiliary_skill_reflect_model" as const,
    label: "技能反思模型",
    hint: "技能执行后反思；留空则使用主模型",
  },
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
  label: string;
  hint: string;
}>;

export type AuxiliaryModelValues = Record<(typeof AUXILIARY_MODEL_FIELDS)[number]["key"], string>;

export function emptyAuxiliaryModels(): AuxiliaryModelValues {
  return {
    auxiliary_vision_model: "",
    auxiliary_web_extract_model: "",
    auxiliary_compression_model: "",
    auxiliary_title_generation_model: "",
    auxiliary_approval_model: "",
    auxiliary_curator_model: "",
    auxiliary_skill_reflect_model: "",
  };
}

export function auxiliaryModelsFromConfig(llm: AppConfig["llm"]): AuxiliaryModelValues {
  const base = emptyAuxiliaryModels();
  for (const field of AUXILIARY_MODEL_FIELDS) {
    base[field.key] = llm[field.key] ?? "";
  }
  return base;
}

export function hasAuxiliaryModels(values: AuxiliaryModelValues): boolean {
  return Object.values(values).some((v) => v.trim().length > 0);
}
