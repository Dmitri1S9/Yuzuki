# graph_extract — Kyoka Jiro (My Hero Academia), schema v2

run_id=jiro-v2, model=qwen3.5:9b, temperature=0.0, num_ctx=8192.

## Scope

Same page set and same 3-8 sentence chunking as the v1 run (no re-experimentation this time, per instruction). See v1's REPORT.md / config.yaml comment for why this page set (pages ABOUT Jiro, not all 737 pages that merely mention her name) was chosen.

- Kyoka Jiro: 11500 chars after cleaning
- Kyoka Jiro/Relationships: 20122 chars after cleaning
- Kyoka Jiro/Synopsis: 85048 chars after cleaning
- Earphone Jack: 2581 chars after cleaning
- Kyotoku Jiro: 1828 chars after cleaning
- Mika Jiro: 2670 chars after cleaning
- Jiro House: 388 chars after cleaning
- Momo Yaoyorozu, Kyoka Jiro & Denki Kaminari vs. Villains: 4675 chars after cleaning
- Kyoka Jiro & Koji Koda vs. Hizashi Yamada: 3026 chars after cleaning
- Enji Todoroki, Keigo Takami, Kyoka Jiro and Fumikage Tokoyami vs. All For One: 20240 chars after cleaning

## A. Timing

This invocation: 0 LLM calls in 0.0s. Total accumulated in Neo4j for run_id=jiro-v2: 119 ACTION edges, 4 DESCRIBED_AS edges.

Wall-clock span from the first to the last edge's `created_at` (covers every invocation this run took, crash-resumed or not): 32.2min.

Jiro's total processed text: 152078 chars across 182 chunks (chunks are independent LLM calls, no shared prefix across chunks beyond the instruction+few-shot+roster block, which IS identical and at the front of every prompt per the ordering instruction -- prefix cache should apply to that shared part).

### Projections (1933s for one character)
- 100 characters: 3222.0min (53.7h)
- 50 universes x 100 characters: 111.9 days, sequential, one GPU.

## B. Comparison with the v1 run

No v1 ACTION edges found in Neo4j (the v1 run was stopped before it reached the Neo4j-write stage when this v2 rewrite was requested, so there is nothing to compare against -- see the reply message for the few example edges v1 produced on individual test chunks before that point).

v2 (this run): 119 edges, 119 valid source (100% valid).

v2 rule-violation checks (post hoc, on what actually got written -- the schema itself blocks a target/subject that isn't a noun via the field description, this checks whether the model still slipped past it):
  - target_looks_like_a_clause (>4 words): 2/119
  - bare_generic_noun_not_resolved_to_people: 0/119

## C. action_raw -> action generalization

| action_raw | action | count |
|---|---|---:|
| is | be | 3 |
| dismissed | dismiss | 2 |
| expressed | express | 2 |
| expressed their support for | support | 2 |
| attack | attack | 2 |
| watches | watch | 2 |
| yells | yell | 2 |
| tells | tell | 2 |
| punished | punish | 2 |
| started taking an interest in | like | 1 |
| engages in | engage | 1 |
| teaches | teach | 1 |
| combat | combat | 1 |
| agreeing | agree | 1 |
| may suffer | suffer | 1 |
| may experience | experience | 1 |
| become | become | 1 |
| says | say | 1 |
| was ... from | make | 1 |
| allowing | allow | 1 |
| defeat | defeat | 1 |
| pass | pass | 1 |
| are | be | 1 |
| tried to project | project | 1 |
| likes | like | 1 |
| fell in love with | love | 1 |
| adopted | adopt | 1 |
| started playing | play | 1 |
| wanted to be | want | 1 |
| getting married | marry | 1 |
| fell in love with | like | 1 |
| desire was for her to follow their footsteps and become | want | 1 |
| developed an interest | develop | 1 |
| decided | decide | 1 |
| wanted | want | 1 |
| were happy | be happy | 1 |
| let | let | 1 |
| participates | participate | 1 |
| reveals | reveal | 1 |
| threatened | threaten | 1 |
| deception | deceive | 1 |
| locate | locate | 1 |
| indicating | indicate | 1 |
| advances | advance | 1 |
| ready to be used | be ready | 1 |
| announces | announce | 1 |
| explains | explain | 1 |
| fends off | fend off | 1 |
| responds | respond | 1 |
| warping | warp | 1 |
| invade | invade | 1 |
| calls | call | 1 |
| watching | watch | 1 |
| sitting still | sit | 1 |
| comments | comment | 1 |
| averts her eyes | avert | 1 |
| carry out their music and dance performance | perform | 1 |
| put up a flashy introduction | introduce | 1 |
| being a huge hit | hit | 1 |
| pump the audience | entertain | 1 |
| thinks back | think | 1 |
| telling | tell | 1 |
| support | support | 1 |
| dedicates herself | dedicate | 1 |
| hold | hold | 1 |
| chooses | choose | 1 |
| is placed | be placed | 1 |
| leads | lead | 1 |
| wants | want | 1 |
| charges | charge | 1 |
| tries to flee | flee | 1 |
| trys to flee | flee | 1 |
| witnessed | witness | 1 |
| agrees | agree | 1 |
| uses | use | 1 |
| informs | inform | 1 |
| suggests | suggest | 1 |
| reports | report | 1 |
| asked | ask | 1 |
| asking | ask | 1 |
| was | be | 1 |
| were | be | 1 |
| convince | convince | 1 |
| carries | carry | 1 |
| encourages | encourage | 1 |
| punched | attack | 1 |
| complimented | compliment | 1 |
| gifted | gift | 1 |
| assisting | assist | 1 |
| receiving special invite tickets | invite | 1 |
| stabbed | stab | 1 |
| encourage | encourage | 1 |
| get on | get on | 1 |
| learn | learn | 1 |
| considers | consider | 1 |
| gains | gain | 1 |
| expresses | express | 1 |
| feel | feel | 1 |
| rushes | rush | 1 |
| hitting | hit | 1 |
| blasts | blast | 1 |
| realizes | realize | 1 |
| scattering | scatter | 1 |
| confirms | confirm | 1 |
| shouts | shout | 1 |
| begins to speak | speak | 1 |
| had left | leave | 1 |
| decides | decide | 1 |
| is able to recognize | recognize | 1 |

## D. All ACTION edges where Kyoka Jiro is subject or target

48 edges.

| subject | action | manner | target | complement | modality | neg | source |
|---|---|---|---|---|---|:-:|---|
| Kyoka Jiro | like |  | tea |  | wants |  | Kyoka recently started taking an interest in tea, likely from spending time with Momo. |
| Kyoka Jiro | engage |  | music-related work |  | did |  | After becoming a Pro Hero, Kyoka frequently engages in music-related work, as she finds her regular work growi |
| Kyoka Jiro | teach |  | None | bass and guitar | did |  | She also teaches Eri to play bass and guitar on her days off. |
| Kyoka Jiro | suffer |  | damage |  | can |  | Like any other part of her body, however, the Earphone Jacks are susceptible to damage and may suffer from ove |
| Kyoka Jiro | experience |  | sound overload |  | can |  | Additionally, if Kyoka plugs her jacks into a surface and detects a very loud sound impacting it, such as an e |
| Kyoka Jiro | become |  | incapacitated |  | can |  | Additionally, if Kyoka plugs her jacks into a surface and detects a very loud sound impacting it, such as an e |
| Kyoka Jiro | play |  | instruments |  | did |  | Kyotoku and Mika's love for music was inherited by Kyoka who started playing instruments at a young age. |
| Kyoka Jiro | want |  | hero |  | wants |  | Believing that her parents' desire was for her to follow their footsteps and become a musician, Kyoka was apol |
| Kyotoku Jiro | want |  | Kyoka Jiro | musician | wants |  | Believing that her parents' desire was for her to follow their footsteps and become a musician, Kyoka was apol |
| Kyotoku Jiro | support |  | Kyoka Jiro | pursue her dreams | did |  | However, Kyotoku and Mika dismissed her apologies and expressed their support for Kyoka to pursue her dreams. |
| Mika Jiro | support |  | Kyoka Jiro | pursue her dreams | did |  | However, Kyotoku and Mika dismissed her apologies and expressed their support for Kyoka to pursue her dreams. |
| Kyoka Jiro | develop |  | music |  | did |  | At a young age, thanks to the influence of her parents, Kyoka developed an interest in music, eventually learn |
| Kyoka Jiro | decide |  | hero |  | did |  | Despite her parents desires for her to become a musician, she decided to become a hero instead because she wan |
| Kyoka Jiro | want |  | None |  | wants |  | Despite her parents desires for her to become a musician, she decided to become a hero instead because she wan |
| None | be happy |  | Kyoka Jiro |  | did |  | When she told her parents about her plans, they were happy for her and let her walk her own path. |
| None | let |  | Kyoka Jiro | walk her own path | did |  | When she told her parents about her plans, they were happy for her and let her walk her own path. |
| Kyoka Jiro | participate |  | the Quirk Apprehension Test | taught by Shota Aizawa | did |  | Kyoka participates in the Quirk Apprehension Test taught by Shota Aizawa, doing her best after the teacher thr |
| Kyoka Jiro | call |  | None | idiots | did |  | Kyoka then calls Denki and Minoru idiots. |
| Kyoka Jiro | watch |  | None | cheer-lead | did |  | During the recreational events, Kyoka is seen sitting still in her cheerleader outfit while watching Mina Ashi |
| Kyoka Jiro | sit |  |  | in her cheerleader outfit | did |  | During the recreational events, Kyoka is seen sitting still in her cheerleader outfit while watching Mina Ashi |
| Kyoka Jiro | comment |  |  | that she might look away the entire time | did |  | As the match between Ochaco and Katsuki begins, Kyoka comments that she might look away the entire time. |
| Kyoka Jiro | avert |  | the match |  | did |  | During the match between Ochaco and Katsuki, Kyoka averts her eyes from the match when seeing Katsuki's explos |
| Kyoka Jiro | watch |  | the closing ceremony |  | did |  | Kyoka along with her class watches the closing ceremony of U.A.'s Sports Festival. |
| Kyoka Jiro | think |  | None |  | did |  | As the rest of the audience cheer on, Kyoka thinks back to telling her parents her plans on becoming a hero. |
| Kyoka Jiro | tell |  | None | plans | did |  | As the rest of the audience cheer on, Kyoka thinks back to telling her parents her plans on becoming a hero. |
| None | support |  | Kyoka Jiro |  | did |  | Kyoka's mother and father support her decision saying that she can do whatever she wants. |
| Kyoka Jiro | dedicate |  |  | enjoying the festival with her friends | did |  | Once their performance is over, Kyoka dedicates herself to enjoying the festival with her friends. |
| Kyoka Jiro | be placed |  | None |  | did |  | As the teams are set, Kyoka is placed with Rikido, Hanta Sero and Katsuki Bakugo, who leads the team. |
| None | tell |  | Kyoka Jiro | to pick up on the sounds coming from the Class 1-B team and to figure out their location | did |  | He tells Kyoka to pick up on the sounds coming from the Class 1-B team and to figure out their location. |
| Kyoka Jiro | use |  | her Quirk |  | did |  | Kyoka uses her Quirk to locate more people but informs her companions that she hasn't detected anyone besides  |
| Kyoka Jiro | inform |  | None | no one else | did |  | Kyoka uses her Quirk to locate more people but informs her companions that she hasn't detected anyone besides  |
| Eijiro Kirishima | ask |  | Kyoka Jiro |  | did |  | Eijiro also asked Kyoka to sing when others were also asking and was soon blown away by her talent like the re |
| None | ask |  | Kyoka Jiro |  | did |  | Eijiro also asked Kyoka to sing when others were also asking and was soon blown away by her talent like the re |
| Kyoka Jiro | convince |  | Koji Koda | use his Quirk to talk to bugs of the forest | did |  | Although Koji is very shy and terrified of insects, Kyoka's words and example of bravery convince him to use h |
| Koji Koda | carry |  | Kyoka Jiro |  | did |  | Nevertheless, Koji later carries an injured Kyoka through the forest to cross the escape gate, and together th |
| Koji Koda | encourage |  | Kyoka Jiro |  | did |  | During the festival, Koji encourages Kyoka to play giving her more confidence. |
| Kyoka Jiro | attack |  | Hanta Sero |  | did |  | Kyoka also punched Hanta after likening Momo's Quirk to defecation during their Quirk Training Camp. |
| Kyoka Jiro | compliment |  | Hanta Sero | dorm room design | did |  | Another scene they shared was when Kyoka complimented Hanta for his unexpected dorm room design. |
| Hanta Sero | gift |  | Kyoka Jiro | scarf | did |  | Hanta also gifted her a scarf with a unique, Asian flare for Kyoka during the surprise exchange gift moment on |
| Kyoka Jiro | assist |  | None |  | did |  | The two were also on the same team in the Joint Training Battle, alongside Katsuki and Rikido, with Hanta assi |
| Kyoka Jiro | encourage |  | Minoru Mineta |  | did |  | When the group suggested for Minoru to climb on the outside of the hijacked I-Island Central Tower in order to |
| Kyoka Jiro | get on |  | Yuga Aoyama |  | did |  | While they aren't seen interacting often, Kyoka and Yuga appear to get on as fellow classmates. |
| Kyoka Jiro | punish |  | Yuga Aoyama |  | did |  | Although during the best room competition, when Yuga commented that her room was unladylike, she punished him  |
| Kyoka Jiro | punish |  | Denki Kaminari |  | did |  | Although during the best room competition, when Yuga commented that her room was unladylike, she punished him  |
| Kyoka Jiro | learn |  | Yuga Aoyama | unwilling mole for All For One who was responsible for the U.S.J. Incident and the Vanguard Action Squad Invasion | did |  | Like the rest of her classmates, Kyoka was deeply shocked and distressed to learn that Yuga was an unwilling m |
| Kyoka Jiro | consider |  | Yuga Aoyama | one of her friends | did |  | While fighting All For One, Kyoka expresses her outrage that he was the one responsible for making her friends |
| Kyoka Jiro | gain |  | desire | to forgive Yuga and help him redeem himself by taking down All For One together | did |  | After learning the whole story however, Kyoka gains the desire to forgive Yuga and help him redeem himself by  |
| Kyoka Jiro | express |  | outrage |  | did |  | While fighting All For One, Kyoka expresses her outrage that he was the one responsible for making her friends |

## E. All DESCRIBED_AS for Kyoka Jiro

1 traits.

- **shy**, said by narrator — "Kyoka's personality describes her as a "shy rock fan"."

## F. 20 random edges for manual review

- None --[be]--> Hizashi Yamada (disappointed) [did] — "Recovery Girl, on the other hand, is disappointed in Present Mic for allowing bugs to defeat him."
- Koji Koda --[combat]--> Hizashi Yamada [did] — "(To Koji about using his Quirk to combat Present Mic) "If you do this, we just might win. But there's no time to hesitate, so do it now! You"
- None --[leave]--> All For One [did] — "It turns out that Kyudai Garaki had left All For One a reverse-engineered version of the Quirk-Destroying Drug that Tomura had stolen from t"
- Mashirao Ojiro --[report]--> None [did] — "Meanwhile, Mashirao reports that there is no signal."
- None --[agree]-->  [did] — "Given the situation, Izuku suggests they should do is confirm the status of the people who were absorbed before escaping from the place, and"
- None --[announce]--> Class 1-A [did] — "Shota announces to the Class 1-A that they will partake in rescue training at an outside facility."
- None --[indicate]--> Denki Kaminari [did] — "During the battle, Kyoka uses her Earphone Jack to locate the rival team, indicating it to Denki, who advances with his Quirk ready to be us"
- Kyotoku Jiro --[like]--> rock music [did] — "Like his daughter, Kyotoku likes rock music and he is also a composer."
- None --[agree]--> host a live show for the U.A. School Festival [did] — "(To her classmates, agreeing to host a live show for the U.A. School Festival) "Turning down... all these requests... wouldn't make me much "
- None --[flee]--> None [did] — "Team 3 tries to flee with as many civilians as they can carry but are helpless after the transformation catches up to them and is consumed a"
- Kyoka Jiro --[think]--> None [did] — "As the rest of the audience cheer on, Kyoka thinks back to telling her parents her plans on becoming a hero."
- All For One --[decide]-->  [did] — "With his original body having served its purpose and destined to be scrapped anyway, he decides to test something out."
- None --[warp]--> None [did] — "Kurogiri responds by warping the class to the various areas in the facility."
- Enji Todoroki --[scatter]--> None [did] — "Kamui pushes some of them out of the way just as Endeavor comes down with another attack, scattering the nearby Heroes and Villains in every"
- Kyoka Jiro --[want]--> hero [wants] — "Believing that her parents' desire was for her to follow their footsteps and become a musician, Kyoka was apologetic when she confessed that"
- Class 1-A --[introduce]-->  [did] — "They manage to put up a flashy introduction and manage to pump the audience with their signing and dancing."
- None --[respond]--> None [did] — "Kurogiri responds by warping the class to the various areas in the facility."
- None --[support]--> Kyoka Jiro [did] — "Kyoka's mother and father support her decision saying that she can do whatever she wants."
- None --[deceive]--> None [did] — "In the end she Ranked 17th in the test, so in theory she is spared from being expelled, although like most students she is surprised when Sh"
- Kyotoku Jiro --[love]--> Mika's musical talents [did] — "At some point, Kyotoku fell in love with Mika's musical talents, which led to them getting married and have a daughter named Kyoka."

## G. Invalid source_sentence share

ACTION: 0/119 invalid (0%)
DESCRIBED_AS: 0/4 invalid (0%)

## H. Cypher query — Kyoka Jiro's graph, this run

```cypher
MATCH (n)-[r]-(m)
WHERE (n.name = "Kyoka Jiro" OR m.name = "Kyoka Jiro")
  AND r.run_id = "jiro-v2"
RETURN n, r, m
```
