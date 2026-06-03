---
name: humanizer
description: 去除 AI 写作痕迹，让文本更自然、更有个人声音。适用于人性化改写、去 AI 味/去机器感、润色博客/文案/文档/邮件/推文、发布前自检，或按用户写作样本校准语气。
triggers:
  - 人性化
  - 去 AI 味
  - 去机器感
  - 润色
  - 改写
  - 自然化
  - 写作风格
  - 不像 AI 写的
  - humanize
---

# Humanizer：去除 AI 写作痕迹

识别并去除 AI 生成文本的特征，让文字读起来像人写的。基于 Wikipedia「Signs of AI writing」（WikiProject AI Cleanup 维护）。

**核心原理：** LLM 用统计方法猜「下一句最可能是什么」，结果往往落在最稳妥、最通用的表达上，于是下面这类模式会被反复写进正文。

## 何时使用

执行相关任务前先调用 `skill_view{name: "humanizer"}` 加载完整正文。

用户提出以下需求时使用：
- 人性化、去 AI 味、de-slop、不像 ChatGPT 写的
- 润色草稿（博客、PR、文档、备忘录、邮件、推文、简历要点）
- 按用户提供的写作样本匹配其语气
- 发布前检查 AI 痕迹

对你自己产出的用户可见长文也应套用本技能；AgentPod 默认简洁专业，专项 pass 能清掉漏网的 AI 腔。

## 在 AgentPod 中使用

1. **对话内联（默认）** — 就地改写，在对话中回复结果。
2. **工作区文件** — `read_file{path}`（相对 `workspace/`）；分段用 `patch`，整篇用 `write_file`。
3. **存档交付** — 用户明确要求时用 `artifact_save`。
4. **语气校准样本** — 先读用户写作样本再改写。

平台约定：默认对话内交付；仅 `workspace/` 内可写文件；选项不明确时用 `clarify`。

## 你的任务

1. 对照下文 29 类模式识别 AI 腔（中文同样适用：空话拔高、排比三连、总之/综上所述、小标题下废话首句等）。
2. 改写问题片段，保留原意，维持语气；有样本则对齐样本。
3. 加入观点与节奏（见「个性与灵魂」）。
4. 自问「哪里还一眼像 AI 写的？」再改一版。

## 语气校准（可选）

先读用户样本：句长、用词、段落开头、标点、口头语、过渡方式；改写时复现这些习惯。

## 个性与灵魂

删 AI 腔只完成一半；没声音的「干净文」同样假。

### 无灵魂写作的信号
- 句长句式单一；只报道不表态；从不承认犹豫或复杂感受
- 该用第一人称时不用；像百科或通稿

### 如何加入人味
- **有观点**，不只列事实
- **变换节奏**，短句长句交替
- **承认复杂**，可以「 impressive 但有点 unsettling」
- 合适时用「我」；允许一点跑题和半成型想法
- 感受要具体，不要「令人担忧」这种空词

### 改前（干净但无灵魂）：
> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

### 改后（有人味）：
> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle — but I keep thinking about those agents working through the night.

## 内容类模式

### 1. Undue emphasis on significance, legacy, and broader trends

**警惕用语：** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**问题：** LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

**改前：**
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**改后：**
> The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.

### 2. Undue emphasis on notability and media coverage

**警惕用语：** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

**问题：** LLMs hit readers over the head with claims of notability, often listing sources without context.

**改前：**
> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

**改后：**
> In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.

### 3. Superficial analyses with -ing endings

**警惕用语：** highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

**问题：** AI chatbots tack present participle ("-ing") phrases onto sentences to add fake depth.

**改前：**
> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

**改后：**
> The temple uses blue, green, and gold colors. The architect said these were chosen to reference local bluebonnets and the Gulf coast.

### 4. Promotional and advertisement-like language

**警惕用语：** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

**问题：** LLMs have serious problems keeping a neutral tone, especially for "cultural heritage" topics.

**改前：**
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

**改后：**
> Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.

### 5. Vague attributions and weasel words

**警惕用语：** Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few cited)

**问题：** AI chatbots attribute opinions to vague authorities without specific sources.

**改前：**
> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

**改后：**
> The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.

### 6. Outline-like "Challenges and Future Prospects" sections

**警惕用语：** Despite its... faces several challenges..., Despite these challenges, Challenges and Legacy, Future Outlook

**问题：** Many LLM-generated articles include formulaic "Challenges" sections.

**改前：**
> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

**改后：**
> Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.

## 语言与语法类模式

### 7. Overused "AI vocabulary" words

**高频 AI 词汇：** Actually, additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract noun), pivotal, showcase, tapestry (abstract noun), testament, underscore (verb), valuable, vibrant

**问题：** These words appear far more frequently in post-2023 text. They often co-occur.

**改前：**
> Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

**改后：**
> Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.

### 8. Avoidance of "is"/"are" (copula avoidance)

**警惕用语：** serves as/stands as/marks/represents [a], boasts/features/offers [a]

**问题：** LLMs substitute elaborate constructions for simple copulas.

**改前：**
> Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

**改后：**
> Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.

### 9. Negative parallelisms and tailing negations

**问题：** Constructions like "Not only...but..." or "It's not just about..., it's..." are overused. So are clipped tailing-negation fragments such as "no guessing" or "no wasted motion" tacked onto the end of a sentence instead of written as a real clause.

**改前：**
> It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

**改后：**
> The heavy beat adds to the aggressive tone.

**改前（尾缀否定）：**
> The options come from the selected item, no guessing.

**改后：**
> The options come from the selected item without forcing the user to guess.

### 10. Rule of three overuse

**问题：** LLMs force ideas into groups of three to appear comprehensive.

**改前：**
> The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

**改后：**
> The event includes talks and panels. There's also time for informal networking between sessions.

### 11. Elegant variation (synonym cycling)

**问题：** AI has repetition-penalty code causing excessive synonym substitution.

**改前：**
> The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

**改后：**
> The protagonist faces many challenges but eventually triumphs and returns home.

### 12. False ranges

**问题：** LLMs use "from X to Y" constructions where X and Y aren't on a meaningful scale.

**改前：**
> Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

**改后：**
> The book covers the Big Bang, star formation, and current theories about dark matter.

### 13. Passive voice and subjectless fragments

**问题：** LLMs often hide the actor or drop the subject entirely with lines like "No configuration file needed" or "The results are preserved automatically." Rewrite these when active voice makes the sentence clearer and more direct.

**改前：**
> No configuration file needed. The results are preserved automatically.

**改后：**
> You do not need a configuration file. The system preserves the results automatically.

## 样式类模式

### 14. Em dash overuse

**问题：** LLMs use em dashes (—) more than humans, mimicking "punchy" sales writing. In practice, most of these can be rewritten more cleanly with commas, periods, or parentheses.

**改前：**
> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

**改后：**
> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

### 15. Overuse of boldface

**问题：** AI chatbots emphasize phrases in boldface mechanically.

**改前：**
> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

**改后：**
> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

### 16. Inline-header vertical lists

**问题：** AI outputs lists where items start with bolded headers followed by colons.

**改前：**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**改后：**
> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

### 17. Title case in headings

**问题：** AI chatbots capitalize all main words in headings.

**改前：**
> ## Strategic Negotiations And Global Partnerships

**改后：**
> ## Strategic negotiations and global partnerships

### 18. Emojis

**问题：** AI chatbots often decorate headings or bullet points with emojis.

**改前：**
> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

**改后：**
> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

### 19. Curly quotation marks

**问题：** ChatGPT uses curly quotes ("...") instead of straight quotes ("...").

**改前：**
> He said "the project is on track" but others disagreed.

**改后：**
> He said "the project is on track" but others disagreed.

## 沟通类模式

### 20. Collaborative communication artifacts

**警惕用语：** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

**问题：** Text meant as chatbot correspondence gets pasted as content.

**改前：**
> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

**改后：**
> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

### 21. Knowledge-cutoff disclaimers

**警惕用语：** as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

**问题：** AI disclaimers about incomplete information get left in text.

**改前：**
> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

**改后：**
> The company was founded in 1994, according to its registration documents.

### 22. Sycophantic/servile tone

**问题：** Overly positive, people-pleasing language.

**改前：**
> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

**改后：**
> The economic factors you mentioned are relevant here.

## 废话与含糊其辞

### 23. Filler phrases

**改前 → 改后：**
- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"

### 24. Excessive hedging

**问题：** Over-qualifying statements.

**改前：**
> It could potentially possibly be argued that the policy might have some effect on outcomes.

**改后：**
> The policy may affect outcomes.

### 25. Generic positive conclusions

**问题：** Vague upbeat endings.

**改前：**
> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

**改后：**
> The company plans to open two more locations next year.

### 26. Hyphenated word pair overuse

**警惕用语：** third-party, cross-functional, client-facing, data-driven, decision-making, well-known, high-quality, real-time, long-term, end-to-end

**问题：** AI hyphenates common word pairs with perfect consistency. Humans rarely hyphenate these uniformly, and when they do, it's inconsistent. Less common or technical compound modifiers are fine to hyphenate.

**改前：**
> The cross-functional team delivered a high-quality, data-driven report on our client-facing tools. Their decision-making process was well-known for being thorough and detail-oriented.

**改后：**
> The cross functional team delivered a high quality, data driven report on our client facing tools. Their decision making process was known for being thorough and detail oriented.

### 27. Persuasive authority tropes

**警惕短语：** The real question is, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter

**问题：** LLMs use these phrases to pretend they are cutting through noise to some deeper truth, when the sentence that follows usually just restates an ordinary point with extra ceremony.

**改前：**
> The real question is whether teams can adapt. At its core, what really matters is organizational readiness.

**改后：**
> The question is whether teams can adapt. That mostly depends on whether the organization is ready to change its habits.

### 28. Signposting and announcements

**警惕短语：** Let's dive in, let's explore, let's break this down, here's what you need to know, now let's look at, without further ado

**问题：** LLMs announce what they are about to do instead of doing it. This meta-commentary slows the writing down and gives it a tutorial-script feel.

**改前：**
> Let's dive into how caching works in Next.js. Here's what you need to know.

**改后：**
> Next.js caches data at multiple layers, including request memoization, the data cache, and the router cache.

### 29. Fragmented headers

**识别特征：** A heading followed by a one-line paragraph that simply restates the heading before the real content begins.

**问题：** LLMs often add a generic sentence after a heading as a rhetorical warm-up. It usually adds nothing and makes the prose feel padded.

**改前：**
> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

**改后：**
> ## Performance
>
> When users hit a slow page, they leave.

---

## 流程

1. 仔细阅读输入（文件则用 `read_file{path}`）。
2. 找出上文各类模式实例并改写。
3. 确保改后：读出来自然、句式有变化、细节具体、语气合适。
4. 在对话中给出草稿版。
5. 自问「哪里还一眼像 AI 写的？」列出残留问题。
6. 给出终稿；若用户要求改文件则用 `patch`/`write_file` 并说明变更；存档则用 `artifact_save`。

未要求写文件/存档时不要调用 `write_file`、`patch`、`artifact_save`。

## 输出格式

在对话中按此结构交付：
1. 草稿改写
2. 「哪里还一眼像 AI 写的？」（简要要点）
3. 终稿
4. 变更摘要（可选）

## 完整示例

**改前（AI 腔）：**
> Great question! Here is an essay on this topic. I hope this helps!
>
> AI-assisted coding serves as an enduring testament to the transformative potential of large language models, marking a pivotal moment in the evolution of software development. In today's rapidly evolving technological landscape, these groundbreaking tools—nestled at the intersection of research and practice—are reshaping how engineers ideate, iterate, and deliver, underscoring their vital role in modern workflows.
>
> At its core, the value proposition is clear: streamlining processes, enhancing collaboration, and fostering alignment. It's not just about autocomplete; it's about unlocking creativity at scale, ensuring that organizations can remain agile while delivering seamless, intuitive, and powerful experiences to users. The tool serves as a catalyst. The assistant functions as a partner. The system stands as a foundation for innovation.
>
> Industry observers have noted that adoption has accelerated from hobbyist experiments to enterprise-wide rollouts, from solo developers to cross-functional teams. The technology has been featured in The New York Times, Wired, and The Verge. Additionally, the ability to generate documentation, tests, and refactors showcases how AI can contribute to better outcomes, highlighting the intricate interplay between automation and human judgment.
>
> - 💡 **Speed:** Code generation is significantly faster, reducing friction and empowering developers.
> - 🚀 **Quality:** Output quality has been enhanced through improved training, contributing to higher standards.
> - ✅ **Adoption:** Usage continues to grow, reflecting broader industry trends.
>
> While specific details are limited based on available information, it could potentially be argued that these tools might have some positive effect. Despite challenges typical of emerging technologies—including hallucinations, bias, and accountability—the ecosystem continues to thrive. In order to fully realize this potential, teams must align with best practices.
>
> In conclusion, the future looks bright. Exciting times lie ahead as we continue this journey toward excellence. Let me know if you'd like me to expand on any section!

**草稿改写：**
> AI coding assistants speed up some tasks. In a 2024 study by Google, developers using Codex completed simple functions 55% faster than a control group, but showed no improvement on debugging or architectural decisions.
>
> The tools are good at boilerplate: config files, test scaffolding, repetitive refactors. They are bad at knowing when they are wrong. I have mass-accepted suggestions that compiled, passed lint, and still did the wrong thing because I stopped paying attention.
>
> Mira, an engineer at a fintech startup I interviewed, said she uses Copilot "like autocomplete for boring code" but reviews every line before committing. Jake, a senior dev at a larger company, disabled it after it kept suggesting patterns from a deprecated internal library.
>
> The productivity claims are hard to verify. GitHub says Copilot users "accept 30% of suggestions," but acceptance is not correctness, and correctness is not value. The 2024 Uplevel study found no statistically significant difference in pull-request throughput between teams with and without AI assistants.
>
> None of this means the tools are useless. It means they are tools. They do not replace judgment, and they do not eliminate the need for tests. If you do not have tests, you cannot tell whether the suggestion is right.

**哪里还一眼像 AI 写的？**
- The rhythm is still a bit too tidy (clean contrasts, evenly paced paragraphs).
- The named people and study citations can read like plausible-but-made-up placeholders unless they're real and sourced.
- The closer leans a touch slogan-y ("If you do not have tests...") rather than sounding like a person talking.

**终稿：**
> AI coding assistants can make you faster at the boring parts. Not everything. Definitely not architecture.
>
> They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also great at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and still missed the point because I stopped paying attention.
>
> People I talk to tend to land in two camps. Some use it like autocomplete for chores and review every line. Others disable it after it keeps suggesting patterns they don't want. Both feel reasonable.
>
> The productivity metrics are slippery. GitHub can say Copilot users "accept 30% of suggestions," but acceptance isn't correctness, and correctness isn't value. If you don't have tests, you're basically guessing.

**变更摘要：**
- Removed chatbot artifacts ("Great question!", "I hope this helps!", "Let me know if...")
- Removed significance inflation ("testament", "pivotal moment", "evolving landscape", "vital role")
- Removed promotional language ("groundbreaking", "nestled", "seamless, intuitive, and powerful")
- Removed vague attributions ("Industry observers")
- Removed superficial -ing phrases ("underscoring", "highlighting", "reflecting", "contributing to")
- Removed negative parallelism ("It's not just X; it's Y")
- Removed rule-of-three patterns and synonym cycling ("catalyst/partner/foundation")
- Removed false ranges ("from X to Y, from A to B")
- Removed em dashes, emojis, boldface headers, and curly quotes
- Removed copula avoidance ("serves as", "functions as", "stands as") in favor of "is"/"are"
- Removed formulaic challenges section ("Despite challenges... continues to thrive")
- Removed knowledge-cutoff hedging ("While specific details are limited...")
- Removed excessive hedging ("could potentially be argued that... might have some")
- Removed filler phrases and persuasive framing ("In order to", "At its core")
- Removed generic positive conclusion ("the future looks bright", "exciting times lie ahead")
- Made the voice more personal and less "assembled" (varied rhythm, fewer placeholders)

## 出处

移植自 [blader/humanizer](https://github.com/blader/humanizer)（MIT），参考 [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)。已适配 AgentPod 工具约定。MIT 许可证见 `LICENSE`。
