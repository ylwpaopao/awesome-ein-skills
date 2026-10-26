import {beforeEach, expect, test} from "bun:test";

let api;
beforeEach(async () => {
  const file = Bun.file(new URL("../scripts/ui_helpers.js", import.meta.url));
  expect(await file.exists()).toBe(true);
  api = new Function(`${await file.text()}; return createDictationUI();`)();
});

function ready(target, before = ["old"], added = ["new"]) {
  return {status:"ready", target, plan_id:"a".repeat(64), backup:"/tmp/verified-backup.json",
    backup_sha256:"b".repeat(64), added,
    before:{target,words:before,complete:true,evidence:{identity:"fixture-account",all_terms:true,enabled:true}},
    after:{words:[...before,...added]}};
}

function plaud(initial = ["old"], {truncated = false, failSave = false} = {}) {
  const state = {words:[...initial],input:"",form:false};
  const dialog = {
    locator(selector) {
      if (selector === ".vocabulary-title") return {innerText:async()=>`常用术语 (${state.words.length + (truncated ? 1 : 0)})`};
      if (selector === ".words-item-title") return {allTextContents:async()=>[...state.words]};
      throw Error("unexpected selector " + selector);
    },
    getByRole(role) { if(role !== "switch") throw Error(role); return {getAttribute:async()=>"true"}; },
    getByText(word) {return {waitFor:async()=>{if(!state.words.includes(word)) throw Error("word not saved");}};}
  };
  const tab = {url:async()=>"https://web.plaud.cn/file/fixture",playwright:{
    getByRole(role) {if(role!=="dialog") throw Error(role);return dialog;},
    getByTestId(id) {
      if(id==="setting-glossary-add-button") return {click:async()=>{state.form=true;}};
      if(id==="dialog-confirm-button") return {click:async()=>{if(!failSave)state.words.push(state.input);state.form=false;}};
      throw Error(id);
    },
    getByPlaceholder(label) {if(label!=="请输入术语") throw Error(label);return {fill:async text=>{state.input=text;}};},
    getByText(label) {if(label!=="保存") throw Error(label);return {click:async()=>{if(state.words.includes(label))throw Error("ambiguous save text");if(!failSave)state.words.push(state.input);state.form=false;}};}
  }};
  return {tab,state};
}

function typeless(initial = ["old"], failSave = false) {
  const state = {words:[...initial],form:false,input:"",indices:new Map(),counter:0};
  const app = {
    async getAXState() {
      state.indices = new Map();
      let id = ++state.counter * 100;
      const row = (indent,body,action)=>{state.indices.set(id,action);return `${"\t".repeat(indent)}${id++} ${body}`;};
      if(state.form) return [row(0,"window Typeless"),row(1,"文本 添加到词典"),
        row(1,"文本栏 (settable) 添加新词","input"),row(1,"按钮 添加词汇","save")].join("\n");
      return [row(0,"window Typeless"),row(1,"文本 PRIVATE_MEETING_BACKGROUND"),
        row(1,"文本 词典"),row(1,"按钮 新词","new"),row(1,"文本 所有"),
        row(1,"文本 自动添加"),row(1,"文本 手动添加"),row(1,"文本栏 (settable) 搜索"),
        row(1,"container"),...state.words.map(word=>row(2,"文本 "+word)),row(0,"关闭按钮")].join("\n");
    },
    async click(index) {
      if(!state.indices.has(index)) throw Error("stale index");
      const action=state.indices.get(index);
      if(action==="new") state.form=true;
      if(action==="save") {if(!failSave)state.words.push(state.input);state.form=false;}
    },
    async paste(text) {state.input=text;}
  };
  return {app,state};
}

const endProof = {allTerms:true,endObserved:true};

test("Plaud reader isolates actual terms and detects truncated inventories", async()=>{
  const full=plaud(["old","保存"]);
  const inventory=await api.readPlaudInventory(full.tab,"fixture-account");
  expect(inventory.words).toEqual(["old","保存"]);
  expect(inventory.complete).toBe(true);
  expect((await api.readPlaudInventory(plaud(["old"],{truncated:true}).tab,"fixture-account")).complete).toBe(false);
});

test("native reader excludes background and needs an observed unfiltered list end", async()=>{
  const fake=typeless(["old","Claude Code"]);
  expect((await api.readTypelessInventory(fake.app,"fixture-account",{})).complete).toBe(false);
  const inventory=await api.readTypelessInventory(fake.app,"fixture-account",endProof);
  expect(inventory.words).toEqual(["old","Claude Code"]);
  expect(inventory.complete).toBe(true);
});

test("missing backup receipt or changed account never mutates Plaud words", async()=>{
  const fake=plaud();
  await expect(api.addPlaudWords(fake.tab,{target:"plaud-cn"})).rejects.toThrow();
  const token=ready("plaud-cn");token.before.evidence.identity="different";
  await expect(api.addPlaudWords(fake.tab,token,"fixture-account")).rejects.toThrow();
  expect(fake.state.words).toEqual(["old"]);
});

test("approved Plaud additions preserve existing terms and skip duplicate desired terms", async()=>{
  const fake=plaud();
  await api.addPlaudWords(fake.tab,ready("plaud-cn"),"fixture-account");
  expect(fake.state.words).toEqual(["old","new"]);
});

test("Plaud save failure stops before subsequent additions", async()=>{
  const fake=plaud(["old"],{failSave:true});
  await expect(api.addPlaudWords(fake.tab,ready("plaud-cn",["old"],["new","later"]),"fixture-account")).rejects.toThrow();
  expect(fake.state.words).toEqual(["old"]);
});

test("a dictionary term named 保存 does not shadow the form save control", async()=>{
  const fake=plaud(["old","保存"]);
  await api.addPlaudWords(fake.tab,ready("plaud-cn",["old","保存"]),"fixture-account");
  expect(fake.state.words).toEqual(["old","保存","new"]);
});

test("native additions derive fresh indices for every form", async()=>{
  const fake=typeless();
  await api.addTypelessWords(fake.app,ready("typeless",["old"],["new","Claude Code"]),"fixture-account",endProof);
  expect(fake.state.words).toEqual(["old","new","Claude Code"]);
});

test("native save failure stops and preserves old terms", async()=>{
  const fake=typeless(["old"],true);
  await expect(api.addTypelessWords(fake.app,ready("typeless"),"fixture-account",endProof)).rejects.toThrow();
  expect(fake.state.words).toEqual(["old"]);
});

test("a changed live word set requires a new preview", async()=>{
  const fake=typeless(["changed"]);
  await expect(api.addTypelessWords(fake.app,ready("typeless"),"fixture-account",endProof)).rejects.toThrow();
  expect(fake.state.words).toEqual(["changed"]);
});
