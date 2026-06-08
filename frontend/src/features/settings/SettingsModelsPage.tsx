import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { getAppConfig, putAppConfig } from "@/api/endpoints";
import type { AppConfigUpdate } from "@/api/types";
import { SettingsSection } from "./SettingsSection";
import {
  AUXILIARY_MODEL_FIELDS,
  auxiliaryModelsFromConfig,
  emptyAuxiliaryModels,
  hasAuxiliaryModels,
  type AuxiliaryModelValues,
} from "./auxiliary-model-fields";

export function SettingsModelsPage() {
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
          AUXILIARY_MODEL_FIELDS.map(({ key }) => [key, auxiliaryModels[key].trim()]),
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
      toast("配置已保存", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title="对话模型（LLM）"
        description={
          <>
            保存到本地 <code className="rounded bg-secondary px-1">~/.agentpod/settings.json</code>
            。API Key 留空则保持已保存的值不变。
          </>
        }
      >
        <div className="grid max-w-xl gap-3">
          <div className="grid gap-1.5">
            <Label>API Base URL</Label>
            <Input
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>主模型</Label>
            <Input value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="gpt-4o" />
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <Label>API Key</Label>
              {llmApiKeyConfigured ? <Badge variant="brand">已配置</Badge> : <Badge>未配置</Badge>}
            </div>
            <Input
              type="password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder={llmApiKeyConfigured ? "留空保持不变" : "sk-..."}
              autoComplete="off"
            />
          </div>

          <CollapsiblePanel
            defaultOpen={auxiliaryOpen}
            onOpenChange={setAuxiliaryOpen}
            summary={
              <span className="flex items-center gap-2">
                场景模型
                {auxiliaryConfiguredCount > 0 ? (
                  <Badge variant="brand">{auxiliaryConfiguredCount} 项已配置</Badge>
                ) : (
                  <span className="text-xs font-normal text-muted-foreground">留空均回退主模型</span>
                )}
              </span>
            }
          >
            <div className="grid gap-3">
              {AUXILIARY_MODEL_FIELDS.map(({ key, label, hint }) => (
                <div key={key} className="grid gap-1.5">
                  <Label>{label}</Label>
                  <Input
                    value={auxiliaryModels[key]}
                    onChange={(e) =>
                      setAuxiliaryModels((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    placeholder={llmModel || "与主模型相同"}
                  />
                  <p className="text-xs text-muted-foreground">{hint}</p>
                </div>
              ))}
            </div>
          </CollapsiblePanel>
        </div>
      </SettingsSection>

      <SettingsSection
        title="向量嵌入（Embedding）"
        description="本地 fastembed 小模型，用于记忆检索与语义搜索；与对话 LLM 无关，首次使用会自动下载。"
      >
        <div className="grid max-w-xl gap-1.5">
          <Label>Embedding 模型</Label>
          <Input
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            placeholder="BAAI/bge-small-zh-v1.5"
          />
        </div>
      </SettingsSection>

      <SettingsSection
        title="第三方工具"
        description="可选。用于 Agent 的网络搜索与网页阅读，留空则对应工具不可用。"
      >
        <div className="grid max-w-xl gap-3">
          <div className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <Label>Tavily Key</Label>
              {tavilyConfigured ? <Badge variant="brand">已配置</Badge> : null}
            </div>
            <Input
              type="password"
              value={tavilyApiKey}
              onChange={(e) => setTavilyApiKey(e.target.value)}
              placeholder={tavilyConfigured ? "留空保持不变" : "可选，网络搜索"}
              autoComplete="off"
            />
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <Label>Jina Key</Label>
              {jinaConfigured ? <Badge variant="brand">已配置</Badge> : null}
            </div>
            <Input
              type="password"
              value={jinaApiKey}
              onChange={(e) => setJinaApiKey(e.target.value)}
              placeholder={jinaConfigured ? "留空保持不变" : "可选，网页阅读"}
              autoComplete="off"
            />
          </div>
        </div>
      </SettingsSection>

      <div>
        <Button variant="primary" disabled={saving} onClick={() => void save()}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          保存配置
        </Button>
      </div>
    </div>
  );
}
