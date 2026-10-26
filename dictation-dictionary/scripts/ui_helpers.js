// Paste this function verbatim into the documented computer-use REPL.
function createDictationUI() {
  const terms = value => {
    if (!Array.isArray(value) || value.some(w => typeof w !== "string" || !w || w.trim() !== w || /[\u0000-\u001f\u007f]/.test(w)))
      throw Error("Invalid words");
    if (new Set(value).size !== value.length) throw Error("Duplicate inventory terms");
    return value;
  };
  const same = (a,b) => a.length === b.length && a.every(w => b.includes(w));
  function snapshot(target, values, identity, proof, complete) {
    if (typeof identity !== "string" || !identity.trim()) throw Error("Observe the account identity first");
    return {target,words:terms(values),complete,evidence:{...proof,identity,observed_at:new Date().toISOString()}};
  }
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object")
      return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));
    return value;
  }
  async function guard(ready, target, current) {
    if (ready?.status !== "ready" || ready.target !== target || !/^[a-f0-9]{64}$/.test(ready.plan_id)
        || !ready.backup?.startsWith("/") || !/^[a-f0-9]{64}$/.test(ready.backup_sha256))
      throw Error("Load a verified backup receipt after the user's approval");
    const plan=ready.plan;
    if (!plan || plan.version !== 1 || plan.target !== target) throw Error("Missing original approved plan");
    const encoded=new TextEncoder().encode(JSON.stringify(canonical(plan),null,2)+"\n");
    const digest=await crypto.subtle.digest("SHA-256",encoded);
    const ident=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
    if (ident !== ready.plan_id || !same(terms(plan.before.words),terms(ready.before.words))
        || plan.before.target !== target || plan.before.evidence.identity !== ready.before.evidence.identity
        || JSON.stringify(plan.after) !== JSON.stringify(ready.after))
      throw Error("Receipt differs from the approved plan");
    const before=terms(ready.before.words), after=terms(ready.after.words), added=terms(ready.added);
    if (!current.complete || !current.evidence.enabled || !current.evidence.all_terms
        || current.evidence.identity !== ready.before.evidence.identity || !same(current.words,before)
        || !same(after,[...before,...added]) || added.some(w=>before.includes(w)))
      throw Error("Live dictionary differs; create a new preview");
    return added;
  }
  async function readPlaudInventory(tab, identity) {
    if (new URL(await tab.url()).origin !== "https://web.plaud.cn") throw Error("Requires PLAUD China");
    const dialog=tab.playwright.getByRole("dialog");
    const title=await dialog.locator(".vocabulary-title").innerText();
    const match=title.match(/常用术语\s*[（(](\d+)[）)]/);
    const values=await dialog.locator(".words-item-title").allTextContents();
    const enabled=await dialog.getByRole("switch").getAttribute("aria-checked") === "true";
    return snapshot("plaud-cn",values,identity,{kind:"count",count:match ? Number(match[1]) : -1,all_terms:true,enabled},
      !!match && Number(match[1]) === values.length && enabled);
  }
  function axRows(text) {
    return text.split("\n").flatMap(line=>{
      const match=line.match(/^(\s*)(\d+)\s+(.+)$/);
      return match ? [{indent:match[1].replaceAll("\t","    ").length,index:Number(match[2]),body:match[3]}] : [];
    });
  }
  async function nativeRows(app) {
    return axRows(await app.getAXState({disableDiffing:true,emit:false}));
  }
  async function readTypelessInventory(app, identity, proof = {}) {
    const rows=await nativeRows(app);
    const searches=rows.map((r,i)=>({r,i})).filter(({r})=>/^(文本栏|text field) .*搜索$/.test(r.body));
    if(searches.length !== 1) throw Error("Open the Typeless dictionary with an empty search field");
    const search=searches[0];
    const list=rows[search.i+1];
    if (!list || list.indent !== search.r.indent || list.body !== "container")
      return snapshot("typeless",[],identity,{kind:"end",at_end:false,all_terms:proof.allTerms===true,enabled:true},false);
    const values=[];
    for(let i=search.i+2;i<rows.length && rows[i].indent>list.indent;i++) {
      const match=rows[i].body.match(/^(文本|text) (.+)$/);
      if(match) values.push(match[2]);
    }
    const complete=proof.allTerms===true && proof.endObserved===true;
    return snapshot("typeless",values,identity,{kind:"end",at_end:proof.endObserved===true,all_terms:proof.allTerms===true,enabled:true},complete);
  }
  async function addPlaudWords(tab, ready, identity) {
    const initial=await readPlaudInventory(tab,identity);
    const added=await guard(ready,"plaud-cn",initial);
    const expected=[...initial.words];
    for (const value of added) {
      const live=await readPlaudInventory(tab,identity);
      if(!live.complete || !same(live.words,expected)) throw Error("Dictionary changed during sync");
      await tab.playwright.getByTestId("setting-glossary-add-button").click();
      await tab.playwright.getByPlaceholder("请输入术语",{exact:true}).fill(value);
      await tab.playwright.getByTestId("dialog-confirm-button").click();
      await tab.playwright.getByRole("dialog").getByText(value,{exact:true}).waitFor({state:"visible"});
      expected.push(value);
      const saved=await readPlaudInventory(tab,identity);
      if(!saved.complete || !same(saved.words,expected)) throw Error("Save was not verified; stop and inspect");
    }
    return readPlaudInventory(tab,identity);
  }
  async function clickNative(app, expression) {
    const matches=(await nativeRows(app)).filter(r=>expression.test(r.body));
    if(matches.length !== 1) throw Error("Expected a unique Typeless control; inspect the current UI");
    await app.click(matches[0].index);
  }
  async function addTypelessWords(app, ready, identity, proof) {
    const initial=await readTypelessInventory(app,identity,proof);
    const added=await guard(ready,"typeless",initial);
    const expected=[...initial.words];
    for (const value of added) {
      const live=await readTypelessInventory(app,identity,proof);
      if(!live.complete || !same(live.words,expected)) throw Error("Dictionary changed during sync");
      await clickNative(app,/^(按钮|button) 新词$/);
      await clickNative(app,/^(文本栏|text field) .*添加新词$/);
      await app.paste(value);
      await clickNative(app,/^(按钮|button) 添加词汇$/);
      expected.push(value);
      const saved=await readTypelessInventory(app,identity,proof);
      if(!saved.complete || !same(saved.words,expected)) throw Error("Save was not verified; stop and inspect");
    }
    return readTypelessInventory(app,identity,proof);
  }
  return {readPlaudInventory,readTypelessInventory,addPlaudWords,addTypelessWords};
}
