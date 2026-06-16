import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { getAppConfig, putAppConfig } from "@/api/endpoints";
import type { AppConfigUpdate } from "@/api/types";
import { SettingsSection } from "./SettingsSection";
import {
  AUXILIARY_MODEL_FIELD_DEFS,
  auxiliaryModelsFromConfig,
  emptyAuxiliaryModels,
  hasAuxiliaryModels,
  type AuxiliaryModelValues,
} from "./auxiliary-model-fields";

const THIRD_PARTY_KEY_FIELDS = [
  {
    id: "tavily",
    href: "https://app.tavily.com/home",
    labelKey: "settings.models.thirdPartyKeys.tavily",
    placeholderKey: "settings.models.thirdPartyKeys.tavilyPlaceholder",
  },
  {
    id: "jina",
    href: "https://jina.ai/api-dashboard/",
    labelKey: "settings.models.thirdPartyKeys.jina",
    placeholderKey: "settings.models.thirdPartyKeys.jinaPlaceholder",
  },
] as const;

type ThirdPartyKeyFieldProps = {
  href: string;
  label: string;
  placeholder: string;
  configured: boolean;
  configuredLabel: string;
  keepEmptyLabel: string;
  value: string;
  onChange: Dispatch<SetStateAction<string>>;
};

function ThirdPartyKeyField({
  href,
  label,
  placeholder,
  configured,
  configuredLabel,
  keepEmptyLabel,
  value,
  onChange,
}: ThirdPartyKeyFieldProps) {
  return (
    <div className="grid gap-1.5">
      <div className="flex items-center gap-2">
        <Label>
          <a
            href={href}
            className="inline-flex items-center gap-1 text-foreground transition-colors hover:text-brand"
          >
            {label}
            <ExternalLink className="size-3 opacity-50" />
          </a>
        </Label>
        {configured ? <Badge variant="brand">{configuredLabel}</Badge> : null}
      </div>
      <Input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={configured ? keepEmptyLabel : placeholder}
        autoComplete="off"
      />
    </div>
  );
}

export function SettingsModelsPage() {
  const { t } = useTranslation();
  const toast = useToast();

  const [llmBaseUrl, setLlmBaseUrl] = useState("https://api.openai.com/v1");
  const [llmModel, setLlmModel] = useState("gpt-4o");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmApiKeyConfigured, setLlmApiKeyConfigured] = useState(false);
  const [auxiliaryModels, setAuxiliaryModels] = useState<AuxiliaryModelValues>(emptyAuxiliaryModels);
  const [auxiliaryOpen, setAuxiliaryOpen] = useState(false);
  const [embeddingModel, setEmbeddingModel] = useState("BAAI/bge-small-zh-v1.5");
  const [tavilyApiKey, setTavilyApiKey] = useState("");
  const [tavilyConfigured, setTavilyConfigured] = useState(false);
  const [jinaApiKey, setJinaApiKey] = useState("");
  const [jinaConfigured, setJinaConfigured] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void getAppConfig().then((cfg) => {
      setLlmBaseUrl(cfg.llm.base_url || "https://api.openai.com/v1");
      setLlmModel(cfg.llm.model || "gpt-4o");
      setLlmApiKeyConfigured(cfg.llm.api_key_configured);
      setLlmApiKey("");
      const aux = auxiliaryModelsFromConfig(cfg.llm);
      setAuxiliaryModels(aux);
      setAuxiliaryOpen(hasAuxiliaryModels(aux));
      setEmbeddingModel(cfg.embedding.model || "BAAI/bge-small-zh-v1.5");
      setTavilyConfigured(cfg.tools.tavily_api_key_configured);
      setTavilyApiKey("");
      setJinaConfigured(cfg.tools.jina_api_key_configured);
      setJinaApiKey("");
    });
  }, []);

  const auxiliaryConfiguredCount = useMemo(
    () => Object.values(auxiliaryModels).filter((v) => v.trim()).length,
    [auxiliaryModels],
  );

  const save = async () => {
    setSaving(true);
    try {
      const body: AppConfigUpdate = {
        llm_base_url: llmBaseUrl.trim(),
        llm_model: llmModel.trim(),
        embedding_model: embeddingModel.trim(),
        ...Object.fromEntries(
          AUXILIARY_MODEL_FIELD_DEFS.map(({ key }) => [key, auxiliaryModels[key].trim()]),
        ),
      };
      if (llmApiKey.trim()) body.llm_api_key = llmApiKey.trim();
      if (tavilyApiKey.trim()) body.tavily_api_key = tavilyApiKey.trim();
      if (jinaApiKey.trim()) body.jina_api_key = jinaApiKey.trim();
      const next = await putAppConfig(body);
      setLlmApiKeyConfigured(next.llm.api_key_configured);
      setLlmApiKey("");
      setTavilyConfigured(next.tools.tavily_api_key_configured);
      setTavilyApiKey("");
      setJinaConfigured(next.tools.jina_api_key_configured);
      setJinaApiKey("");
      toast(t("settings.models.saved"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title={t("settings.models.llm.title")}
        description={t("settings.models.llm.description")}
      >
        <div className="grid max-w-xl gap-3">
          <div className="grid gap-1.5">
            <Label>{t("settings.models.apiBaseUrl")}</Label>
            <Input
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>{t("settings.models.llm.primaryLabel")}</Label>
            <Input value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="gpt-4o" />
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <Label>{t("settings.models.apiKey")}</Label>
              {llmApiKeyConfigured ? (
                <Badge variant="brand">{t("settings.models.llm.configured")}</Badge>
              ) : (
                <Badge>{t("settings.models.llm.notConfigured")}</Badge>
              )}
            </div>
            <Input
              type="password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder={llmApiKeyConfigured ? t("settings.models.llm.keepEmpty") : "sk-..."}
              autoComplete="off"
            />
          </div>

          <CollapsiblePanel
            defaultOpen={auxiliaryOpen}
            onOpenChange={setAuxiliaryOpen}
            summary={
              <span className="flex items-center gap-2">
                {t("settings.models.auxiliary.title")}
                {auxiliaryConfiguredCount > 0 ? (
                  <Badge variant="brand">
                    {t("settings.models.auxiliary.configuredCount", { count: auxiliaryConfiguredCount })}
                  </Badge>
                ) : (
                  <span className="text-xs font-normal text-muted-foreground">
                    {t("settings.models.auxiliary.description")}
                  </span>
                )}
              </span>
            }
          >
            <div className="grid gap-3">
              {AUXILIARY_MODEL_FIELD_DEFS.map(({ key, labelKey, hintKey }) => (
                <div key={key} className="grid gap-1.5">
                  <Label>{t(labelKey)}</Label>
                  <Input
                    value={auxiliaryModels[key]}
                    onChange={(e) =>
                      setAuxiliaryModels((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    placeholder={llmModel || "gpt-4o"}
                  />
                  <p className="text-xs text-muted-foreground">{t(hintKey)}</p>
                </div>
              ))}
            </div>
          </CollapsiblePanel>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t("settings.models.embedding.title")}
        description={t("settings.models.embedding.description")}
      >
        <div className="grid max-w-xl gap-1.5">
          <Label>{t("settings.models.embedding.modelLabel")}</Label>
          <Input
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            placeholder="BAAI/bge-small-zh-v1.5"
          />
        </div>
      </SettingsSection>

      <SettingsSection
        title={t("settings.models.thirdParty.title")}
        description={t("settings.models.thirdParty.description")}
      >
        <div className="grid max-w-xl gap-3">
          {THIRD_PARTY_KEY_FIELDS.map(({ id, href, labelKey, placeholderKey }) => {
            const configured = id === "tavily" ? tavilyConfigured : jinaConfigured;
            const value = id === "tavily" ? tavilyApiKey : jinaApiKey;
            const onChange = id === "tavily" ? setTavilyApiKey : setJinaApiKey;
            return (
              <ThirdPartyKeyField
                key={id}
                href={href}
                label={t(labelKey)}
                placeholder={t(placeholderKey)}
                configured={configured}
                configuredLabel={t("settings.models.llm.configured")}
                keepEmptyLabel={t("settings.models.llm.keepEmpty")}
                value={value}
                onChange={onChange}
              />
            );
          })}
        </div>
      </SettingsSection>

      <div>
        <Button variant="primary" disabled={saving} onClick={() => void save()}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          {t("settings.models.save")}
        </Button>
      </div>
    </div>
  );
}
