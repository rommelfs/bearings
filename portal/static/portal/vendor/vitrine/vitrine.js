/*! Vitrine 0.14.0 | MIT | ecrou-exact/vitrine | See LICENSE and THIRD_PARTY_NOTICES.md */
var Ho=Object.create;var Ia=Object.defineProperty;var Go=Object.getOwnPropertyDescriptor;var Vo=Object.getOwnPropertyNames;var qo=Object.getPrototypeOf,Ko=Object.prototype.hasOwnProperty;var Wo=(n,e)=>()=>{try{return e||n((e={exports:{}}).exports,e),e.exports}catch(t){throw e=0,t}};var Yo=(n,e,t,r)=>{if(e&&typeof e=="object"||typeof e=="function")for(let a of Vo(e))!Ko.call(n,a)&&a!==t&&Ia(n,a,{get:()=>e[a],enumerable:!(r=Go(e,a))||r.enumerable});return n};var Zo=(n,e,t)=>(t=n!=null?Ho(qo(n)):{},Yo(e||!n||!n.__esModule?Ia(t,"default",{value:n,enumerable:!0}):t,n));var Ws=Wo((oh,Ks)=>{function Ds(n){return n instanceof Map?n.clear=n.delete=n.set=function(){throw new Error("map is read-only")}:n instanceof Set&&(n.add=n.clear=n.delete=function(){throw new Error("set is read-only")}),Object.freeze(n),Object.getOwnPropertyNames(n).forEach(e=>{let t=n[e],r=typeof t;(r==="object"||r==="function")&&!Object.isFrozen(t)&&Ds(t)}),n}var Cn=class{constructor(e){e.data===void 0&&(e.data={}),this.data=e.data,this.isMatchIgnored=!1}ignoreMatch(){this.isMatchIgnored=!0}};function Ps(n){return n.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;")}function nt(n,...e){let t=Object.create(null);for(let r in n)t[r]=n[r];return e.forEach(function(r){for(let a in r)t[a]=r[a]}),t}var zl="</span>",Cs=n=>!!n.scope,Bl=(n,{prefix:e})=>{if(n.startsWith("language:"))return n.replace("language:","language-");if(n.includes(".")){let t=n.split(".");return[`${e}${t.shift()}`,...t.map((r,a)=>`${r}${"_".repeat(a+1)}`)].join(" ")}return`${e}${n}`},Cr=class{constructor(e,t){this.buffer="",this.classPrefix=t.classPrefix,e.walk(this)}addText(e){this.buffer+=Ps(e)}openNode(e){if(!Cs(e))return;let t=Bl(e.scope,{prefix:this.classPrefix});this.span(t)}closeNode(e){Cs(e)&&(this.buffer+=zl)}value(){return this.buffer}span(e){this.buffer+=`<span class="${e}">`}},Ms=(n={})=>{let e={children:[]};return Object.assign(e,n),e},Mr=class n{constructor(){this.rootNode=Ms(),this.stack=[this.rootNode]}get top(){return this.stack[this.stack.length-1]}get root(){return this.rootNode}add(e){this.top.children.push(e)}openNode(e){let t=Ms({scope:e});this.add(t),this.stack.push(t)}closeNode(){if(this.stack.length>1)return this.stack.pop()}closeAllNodes(){for(;this.closeNode(););}toJSON(){return JSON.stringify(this.rootNode,null,4)}walk(e){return this.constructor._walk(e,this.rootNode)}static _walk(e,t){return typeof t=="string"?e.addText(t):t.children&&(e.openNode(t),t.children.forEach(r=>this._walk(e,r)),e.closeNode(t)),e}static _collapse(e){typeof e!="string"&&e.children&&(e.children.every(t=>typeof t=="string")?e.children=[e.children.join("")]:e.children.forEach(t=>{n._collapse(t)}))}},Lr=class extends Mr{constructor(e){super(),this.options=e}addText(e){e!==""&&this.add(e)}startScope(e){this.openNode(e)}endScope(){this.closeNode()}__addSublanguage(e,t){let r=e.root;t&&(r.scope=`language:${t}`),this.add(r)}toHTML(){return new Cr(this,this.options).value()}finalize(){return this.closeAllNodes(),!0}};function Qt(n){return n?typeof n=="string"?n:n.source:null}function zs(n){return mt("(?=",n,")")}function Ul(n){return mt("(?:",n,")*")}function jl(n){return mt("(?:",n,")?")}function mt(...n){return n.map(t=>Qt(t)).join("")}function Fl(n){let e=n[n.length-1];return typeof e=="object"&&e.constructor===Object?(n.splice(n.length-1,1),e):{}}function Ln(...n){return"("+(Fl(n).capture?"":"?:")+n.map(r=>Qt(r)).join("|")+")"}function Bs(n){return new RegExp(n.toString()+"|").exec("").length-1}function $l(n,e){let t=n&&n.exec(e);return t&&t.index===0}var Hl=new RegExp(Ln(/\[(?:[^\\\]]|\\.)*\]/,/\(\?<(?![=!])[^>]+>/,/\(\?'[^']+'/,/\(\??/,/\\([1-9][0-9]*)/,/\\./));function Or(n,{joinWith:e}){let t=0;return n.map(r=>{t+=1;let a=t,s=Qt(r),i="";for(;s.length>0;){let o=Hl.exec(s);if(!o){i+=s;break}i+=s.substring(0,o.index),s=s.substring(o.index+o[0].length),o[0][0]==="\\"&&o[1]?i+="\\"+String(Number(o[1])+a):(i+=o[0],(o[0]==="("||/^\(\?[<']/.test(o[0]))&&t++)}return i}).map(r=>`(${r})`).join(e)}var Gl=/\b\B/,Us="[a-zA-Z]\\w*",Ir="[a-zA-Z_]\\w*",js="\\b\\d+(\\.\\d+)?",Fs="(-?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)",$s="\\b(0b[01]+)",Vl="!|!=|!==|%|%=|&|&&|&=|\\*|\\*=|\\+|\\+=|,|-|-=|/=|/|:|;|<<|<<=|<=|<|===|==|=|>>>=|>>=|>=|>>>|>>|>|\\?|\\[|\\{|\\(|\\^|\\^=|\\||\\|=|\\|\\||~",ql=(n={})=>{let e=/^#![ ]*\//;return n.binary&&(n.begin=mt(e,/.*\b/,n.binary,/\b.*/)),nt({scope:"meta",begin:e,end:/$/,relevance:0,"on:begin":(t,r)=>{t.index!==0&&r.ignoreMatch()}},n)},en={begin:"\\\\[\\s\\S]",relevance:0},Kl={scope:"string",begin:"'",end:"'",illegal:"\\n",contains:[en]},Wl={scope:"string",begin:'"',end:'"',illegal:"\\n",contains:[en]},Yl={begin:/\b(a|an|the|are|I'm|isn't|don't|doesn't|won't|but|just|should|pretty|simply|enough|gonna|going|wtf|so|such|will|you|your|they|like|more)\b/},Rn=function(n,e,t={}){let r=nt({scope:"comment",begin:n,end:e,contains:[]},t);r.contains.push({scope:"doctag",begin:"[ ]*(?=(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):)",end:/(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):/,excludeBegin:!0,relevance:0});let a=Ln("I","a","is","so","us","to","at","if","in","it","on",/[A-Za-z]+['](d|ve|re|ll|t|s|n)/,/[A-Za-z]+[-][a-z]+/,/[A-Za-z][a-z]{2,}/);return r.contains.push({begin:mt(/[ ]+/,"(",a,/[.]?[:]?([.][ ]|[ ])/,"){3}")}),r},Zl=Rn("//","$"),Jl=Rn("/\\*","\\*/"),Xl=Rn("#","$"),Ql={scope:"number",begin:js,relevance:0},ec={scope:"number",begin:Fs,relevance:0},tc={scope:"number",begin:$s,relevance:0},nc={scope:"regexp",begin:/\/(?=[^/\n]*\/)/,end:/\/[gimuy]*/,contains:[en,{begin:/\[/,end:/\]/,relevance:0,contains:[en]}]},rc={scope:"title",begin:Us,relevance:0},ac={scope:"title",begin:Ir,relevance:0},sc={begin:"\\.\\s*"+Ir,relevance:0},ic=function(n){return Object.assign(n,{"on:begin":(e,t)=>{t.data._beginMatch=e[1]},"on:end":(e,t)=>{t.data._beginMatch!==e[1]&&t.ignoreMatch()}})},Nn=Object.freeze({__proto__:null,APOS_STRING_MODE:Kl,BACKSLASH_ESCAPE:en,BINARY_NUMBER_MODE:tc,BINARY_NUMBER_RE:$s,COMMENT:Rn,C_BLOCK_COMMENT_MODE:Jl,C_LINE_COMMENT_MODE:Zl,C_NUMBER_MODE:ec,C_NUMBER_RE:Fs,END_SAME_AS_BEGIN:ic,HASH_COMMENT_MODE:Xl,IDENT_RE:Us,MATCH_NOTHING_RE:Gl,METHOD_GUARD:sc,NUMBER_MODE:Ql,NUMBER_RE:js,PHRASAL_WORDS_MODE:Yl,QUOTE_STRING_MODE:Wl,REGEXP_MODE:nc,RE_STARTERS_RE:Vl,SHEBANG:ql,TITLE_MODE:rc,UNDERSCORE_IDENT_RE:Ir,UNDERSCORE_TITLE_MODE:ac});function oc(n,e){n.input[n.index-1]==="."&&e.ignoreMatch()}function lc(n,e){n.className!==void 0&&(n.scope=n.className,delete n.className)}function cc(n,e){e&&n.beginKeywords&&(n.begin="\\b("+n.beginKeywords.split(" ").join("|")+")(?!\\.)(?=\\b|\\s)",n.__beforeBegin=oc,n.keywords=n.keywords||n.beginKeywords,delete n.beginKeywords,n.relevance===void 0&&(n.relevance=0))}function uc(n,e){Array.isArray(n.illegal)&&(n.illegal=Ln(...n.illegal))}function dc(n,e){if(n.match){if(n.begin||n.end)throw new Error("begin & end are not supported with match");n.begin=n.match,delete n.match}}function hc(n,e){n.relevance===void 0&&(n.relevance=1)}var pc=(n,e)=>{if(!n.beforeMatch)return;if(n.starts)throw new Error("beforeMatch cannot be used with starts");let t=Object.assign({},n);Object.keys(n).forEach(r=>{delete n[r]}),n.keywords=t.keywords,n.begin=mt(t.beforeMatch,zs(t.begin)),n.starts={relevance:0,contains:[Object.assign(t,{endsParent:!0})]},n.relevance=0,delete t.beforeMatch},fc=["of","and","for","in","not","or","if","then","parent","list","value"],mc="keyword";function Hs(n,e,t=mc){let r=Object.create(null);return typeof n=="string"?a(t,n.split(" ")):Array.isArray(n)?a(t,n):Object.keys(n).forEach(function(s){Object.assign(r,Hs(n[s],e,s))}),r;function a(s,i){e&&(i=i.map(o=>o.toLowerCase())),i.forEach(function(o){let c=o.split("|");r[c[0]]=[s,gc(c[0],c[1])]})}}function gc(n,e){return e?Number(e):bc(n)?0:1}function bc(n){return fc.includes(n.toLowerCase())}var Ls={},ft=n=>{console.error(n)},Rs=(n,...e)=>{console.log(`WARN: ${n}`,...e)},zt=(n,e)=>{Ls[`${n}/${e}`]||(console.log(`Deprecated as of ${n}. ${e}`),Ls[`${n}/${e}`]=!0)},Mn=new Error;function Gs(n,e,{key:t}){let r=0,a=n[t],s={},i={};for(let o=1;o<=e.length;o++)i[o+r]=a[o],s[o+r]=!0,r+=Bs(e[o-1]);n[t]=i,n[t]._emit=s,n[t]._multi=!0}function yc(n){if(Array.isArray(n.begin)){if(n.skip||n.excludeBegin||n.returnBegin)throw ft("skip, excludeBegin, returnBegin not compatible with beginScope: {}"),Mn;if(typeof n.beginScope!="object"||n.beginScope===null)throw ft("beginScope must be object"),Mn;Gs(n,n.begin,{key:"beginScope"}),n.begin=Or(n.begin,{joinWith:""})}}function vc(n){if(Array.isArray(n.end)){if(n.skip||n.excludeEnd||n.returnEnd)throw ft("skip, excludeEnd, returnEnd not compatible with endScope: {}"),Mn;if(typeof n.endScope!="object"||n.endScope===null)throw ft("endScope must be object"),Mn;Gs(n,n.end,{key:"endScope"}),n.end=Or(n.end,{joinWith:""})}}function xc(n){n.scope&&typeof n.scope=="object"&&n.scope!==null&&(n.beginScope=n.scope,delete n.scope)}function _c(n){xc(n),typeof n.beginScope=="string"&&(n.beginScope={_wrap:n.beginScope}),typeof n.endScope=="string"&&(n.endScope={_wrap:n.endScope}),yc(n),vc(n)}function wc(n){function e(i,o){return new RegExp(Qt(i),"m"+(n.case_insensitive?"i":"")+(n.unicodeRegex?"u":"")+(o?"g":""))}class t{constructor(){this.matchIndexes={},this.regexes=[],this.matchAt=1,this.position=0}addRule(o,c){c.position=this.position++,this.matchIndexes[this.matchAt]=c,this.regexes.push([c,o]),this.matchAt+=Bs(o)+1}compile(){this.regexes.length===0&&(this.exec=()=>null);let o=this.regexes.map(c=>c[1]);this.matcherRe=e(Or(o,{joinWith:"|"}),!0),this.lastIndex=0}exec(o){this.matcherRe.lastIndex=this.lastIndex;let c=this.matcherRe.exec(o);if(!c)return null;let u=c.findIndex((b,m)=>m>0&&b!==void 0),h=this.matchIndexes[u];return c.splice(0,u),Object.assign(c,h)}}class r{constructor(){this.rules=[],this.multiRegexes=[],this.count=0,this.lastIndex=0,this.regexIndex=0}getMatcher(o){if(this.multiRegexes[o])return this.multiRegexes[o];let c=new t;return this.rules.slice(o).forEach(([u,h])=>c.addRule(u,h)),c.compile(),this.multiRegexes[o]=c,c}resumingScanAtSamePosition(){return this.regexIndex!==0}considerAll(){this.regexIndex=0}addRule(o,c){this.rules.push([o,c]),c.type==="begin"&&this.count++}exec(o){let c=this.getMatcher(this.regexIndex);c.lastIndex=this.lastIndex;let u=c.exec(o);if(this.resumingScanAtSamePosition()&&!(u&&u.index===this.lastIndex)){let h=this.getMatcher(0);h.lastIndex=this.lastIndex+1,u=h.exec(o)}return u&&(this.regexIndex+=u.position+1,this.regexIndex===this.count&&this.considerAll()),u}}function a(i){let o=new r;return i.contains.forEach(c=>o.addRule(c.begin,{rule:c,type:"begin"})),i.terminatorEnd&&o.addRule(i.terminatorEnd,{type:"end"}),i.illegal&&o.addRule(i.illegal,{type:"illegal"}),o}function s(i,o){let c=i;if(i.isCompiled)return c;[lc,dc,_c,pc].forEach(h=>h(i,o)),n.compilerExtensions.forEach(h=>h(i,o)),i.__beforeBegin=null,[cc,uc,hc].forEach(h=>h(i,o)),i.isCompiled=!0;let u=null;return typeof i.keywords=="object"&&i.keywords.$pattern&&(i.keywords=Object.assign({},i.keywords),u=i.keywords.$pattern,delete i.keywords.$pattern),u=u||/\w+/,i.keywords&&(i.keywords=Hs(i.keywords,n.case_insensitive)),c.keywordPatternRe=e(u,!0),o&&(i.begin||(i.begin=/\B|\b/),c.beginRe=e(c.begin),!i.end&&!i.endsWithParent&&(i.end=/\B|\b/),i.end&&(c.endRe=e(c.end)),c.terminatorEnd=Qt(c.end)||"",i.endsWithParent&&o.terminatorEnd&&(c.terminatorEnd+=(i.end?"|":"")+o.terminatorEnd)),i.illegal&&(c.illegalRe=e(i.illegal)),i.contains||(i.contains=[]),i.contains=[].concat(...i.contains.map(function(h){return Ec(h==="self"?i:h)})),i.contains.forEach(function(h){s(h,c)}),i.starts&&s(i.starts,o),c.matcher=a(c),c}if(n.compilerExtensions||(n.compilerExtensions=[]),n.contains&&n.contains.includes("self"))throw new Error("ERR: contains `self` is not supported at the top-level of a language.  See documentation.");return n.classNameAliases=nt(n.classNameAliases||{}),s(n)}function Vs(n){return n?n.endsWithParent||Vs(n.starts):!1}function Ec(n){return n.variants&&!n.cachedVariants&&(n.cachedVariants=n.variants.map(function(e){return nt(n,{variants:null},e)})),n.cachedVariants?n.cachedVariants:Vs(n)?nt(n,{starts:n.starts?nt(n.starts):null}):Object.isFrozen(n)?nt(n):n}var Ac="11.12.0",Rr=class extends Error{constructor(e,t){super(e),this.name="HTMLInjectionError",this.html=t}},Nr=Ps,Os=nt,Is=Symbol("nomatch"),Sc=7,qs=function(n){let e=Object.create(null),t=Object.create(null),r=[],a=!0,s="Could not find the language '{}', did you forget to load/include a language module?",i={disableAutodetect:!0,name:"Plain text",contains:[]},o={ignoreUnescapedHTML:!1,throwUnescapedHTML:!1,noHighlightRe:/^(no-?highlight)$/i,languageDetectRe:/\blang(?:uage)?-([\w-]+)\b/i,classPrefix:"hljs-",cssSelector:"pre code",languages:null,__emitter:Lr};function c(w){return o.noHighlightRe.test(w)}function u(w){let k=w.className+" ";k+=w.parentNode?w.parentNode.className:"";let R=o.languageDetectRe.exec(k);if(R){let F=ie(R[1]);return F||(Rs(s.replace("{}",R[1])),Rs("Falling back to no-highlight mode for this block.",w)),F?R[1]:"no-highlight"}return k.split(/\s+/).find(F=>c(F)||ie(F))}function h(w,k,R){let F="",E="";typeof k=="object"?(F=w,R=k.ignoreIllegals,E=k.language):(zt("10.7.0","highlight(lang, code, ...args) has been deprecated."),zt("10.7.0",`Please use highlight(code, options) instead.
https://github.com/highlightjs/highlight.js/issues/2277`),E=w,F=k),R===void 0&&(R=!0);let L={code:F,language:E};Ne("before:highlight",L);let z=L.result?L.result:b(L.language,L.code,R);return z.code=L.code,Ne("after:highlight",z),z}function b(w,k,R,F){let E=Object.create(null);function L(A,N){return A.keywords[N]}function z(){if(!T.keywords){Z.addText(V);return}let A=0;T.keywordPatternRe.lastIndex=0;let N=T.keywordPatternRe.exec(V),O="";for(;N;){O+=V.substring(A,N.index);let $=Ae.case_insensitive?N[0].toLowerCase():N[0],ee=L(T,$);if(ee){let[Se,Et]=ee;if(Z.addText(O),O="",E[$]=(E[$]||0)+1,E[$]<=Sc&&(ot+=Et),Se.startsWith("_"))O+=N[0];else{let At=Ae.classNameAliases[Se]||Se;Q(N[0],At)}}else O+=N[0];A=T.keywordPatternRe.lastIndex,N=T.keywordPatternRe.exec(V)}O+=V.substring(A),Z.addText(O)}function Y(){if(V==="")return;let A=null;if(typeof T.subLanguage=="string"){if(!e[T.subLanguage]){Z.addText(V);return}A=b(T.subLanguage,V,!0,_t[T.subLanguage]),_t[T.subLanguage]=A._top}else A=_(V,T.subLanguage.length?T.subLanguage:null);T.relevance>0&&(ot+=A.relevance),Z.__addSublanguage(A._emitter,A.language)}function B(){T.subLanguage!=null?Y():z(),V=""}function Q(A,N){A!==""&&(Z.startScope(N),Z.addText(A),Z.endScope())}function K(A,N){let O=1,$=N.length-1;for(;O<=$;){if(!A._emit[O]){O++;continue}let ee=Ae.classNameAliases[A[O]]||A[O],Se=N[O];ee?Q(Se,ee):(V=Se,z(),V=""),O++}}function dn(A,N){return A.scope&&typeof A.scope=="string"&&Z.openNode(Ae.classNameAliases[A.scope]||A.scope),A.beginScope&&(A.beginScope._wrap?(Q(V,Ae.classNameAliases[A.beginScope._wrap]||A.beginScope._wrap),V=""):A.beginScope._multi&&(K(A.beginScope,N),V="")),T=Object.create(A,{parent:{value:T}}),T}function hn(A,N,O){let $=$l(A.endRe,O);if($){if(A["on:end"]){let ee=new Cn(A);A["on:end"](N,ee),ee.isMatchIgnored&&($=!1)}if($){for(;A.endsParent&&A.parent;)A=A.parent;return A}}if(A.endsWithParent)return hn(A.parent,N,O)}function Kn(A){return T.matcher.regexIndex===0?(V+=A[0],1):(lt=!0,0)}function Wn(A){let N=A[0],O=A.rule,$=new Cn(O),ee=[O.__beforeBegin,O["on:begin"]];for(let Se of ee)if(Se&&(Se(A,$),$.isMatchIgnored))return Kn(N);return O.skip?V+=N:(O.excludeBegin&&(V+=N),B(),!O.returnBegin&&!O.excludeBegin&&(V=N)),dn(O,A),O.returnBegin?0:N.length}function Yn(A){let N=A[0],O=k.substring(A.index),$=hn(T,A,O);if(!$)return Is;let ee=T;T.endScope&&T.endScope._wrap?(B(),Q(N,T.endScope._wrap)):T.endScope&&T.endScope._multi?(B(),K(T.endScope,A)):ee.skip?V+=N:(ee.returnEnd||ee.excludeEnd||(V+=N),B(),ee.excludeEnd&&(V=N));do T.scope&&Z.closeNode(),!T.skip&&!T.subLanguage&&(ot+=T.relevance),T=T.parent;while(T!==$.parent);return $.starts&&dn($.starts,A),ee.returnEnd?0:N.length}function Zn(){let A=[];for(let N=T;N!==Ae;N=N.parent)N.scope&&A.unshift(N.scope);A.forEach(N=>Z.openNode(N))}let st={};function pn(A,N){let O=N&&N[0];if(V+=A,O==null)return B(),0;if(st.type==="begin"&&N.type==="end"&&st.index===N.index&&O===""){if(V+=k.slice(N.index,N.index+1),!a){let $=new Error(`0 width match regex (${w})`);throw $.languageName=w,$.badRule=st.rule,$}return 1}if(st=N,N.type==="begin")return Wn(N);if(N.type==="illegal"&&!R){let $=new Error('Illegal lexeme "'+O+'" for mode "'+(T.scope||"<unnamed>")+'"');throw $.mode=T,$}else if(N.type==="end"){let $=Yn(N);if($!==Is)return $}if(N.type==="illegal"&&O==="")return N.index===k.length||(V+=`
`),1;if(wt>1e5&&wt>N.index*3)throw new Error("potential infinite loop, way more iterations than matches");return V+=O,O.length}let Ae=ie(w);if(!Ae)throw ft(s.replace("{}",w)),new Error('Unknown language: "'+w+'"');let J=wc(Ae),it="",T=F||J,_t={},Z=new o.__emitter(o);Zn();let V="",ot=0,me=0,wt=0,lt=!1;try{if(Ae.__emitTokens)Ae.__emitTokens(k,Z);else{for(T.matcher.considerAll();;){wt++,lt?lt=!1:T.matcher.considerAll(),T.matcher.lastIndex=me;let A=T.matcher.exec(k);if(!A)break;let N=k.substring(me,A.index),O=pn(N,A);me=A.index+O}pn(k.substring(me))}return Z.finalize(),it=Z.toHTML(),{language:w,value:it,relevance:ot,illegal:!1,_emitter:Z,_top:T}}catch(A){if(A.message&&A.message.includes("Illegal"))return{language:w,value:Nr(k),illegal:!0,relevance:0,_illegalBy:{message:A.message,index:me,context:k.slice(me-100,me+100),mode:A.mode,resultSoFar:it},_emitter:Z};if(a)return{language:w,value:Nr(k),illegal:!1,relevance:0,errorRaised:A,_emitter:Z,_top:T};throw A}}function m(w){let k={value:Nr(w),illegal:!1,relevance:0,_top:i,_emitter:new o.__emitter(o)};return k._emitter.addText(w),k}function _(w,k){k=k||o.languages||Object.keys(e);let R=m(w),F=k.filter(ie).filter(ke).map(B=>b(B,w,!1));F.unshift(R);let E=F.sort((B,Q)=>{if(B.relevance!==Q.relevance)return Q.relevance-B.relevance;if(B.language&&Q.language){if(ie(B.language).supersetOf===Q.language)return 1;if(ie(Q.language).supersetOf===B.language)return-1}return 0}),[L,z]=E,Y=L;return Y.secondBest=z,Y}function p(w,k,R){let F=k&&t[k]||R;w.classList.add("hljs"),w.classList.add(`language-${F}`)}function g(w){let k=null,R=u(w);if(c(R))return;if(Ne("before:highlightElement",{el:w,language:R}),w.dataset.highlighted){console.log("Element previously highlighted. To highlight again, first unset `dataset.highlighted`.",w);return}if(w.children.length>0&&(o.ignoreUnescapedHTML||(console.warn("One of your code blocks includes unescaped HTML. This is a potentially serious security risk."),console.warn("https://github.com/highlightjs/highlight.js/wiki/security"),console.warn("The element with unescaped HTML:"),console.warn(w)),o.throwUnescapedHTML))throw new Rr("One of your code blocks includes unescaped HTML.",w.innerHTML);k=w;let F=k.textContent,E=R?h(F,{language:R,ignoreIllegals:!0}):_(F);w.innerHTML=E.value,w.dataset.highlighted="yes",p(w,R,E.language),w.result={language:E.language,re:E.relevance,relevance:E.relevance},E.secondBest&&(w.secondBest={language:E.secondBest.language,relevance:E.secondBest.relevance}),Ne("after:highlightElement",{el:w,result:E,text:F})}function S(w){o=Os(o,w)}let M=()=>{P(),zt("10.6.0","initHighlighting() deprecated.  Use highlightAll() now.")};function D(){P(),zt("10.6.0","initHighlightingOnLoad() deprecated.  Use highlightAll() now.")}let j=!1;function P(){function w(){P()}if(document.readyState==="loading"){j||window.addEventListener("DOMContentLoaded",w,!1),j=!0;return}document.querySelectorAll(o.cssSelector).forEach(g)}function q(w,k){let R=null;try{R=k(n)}catch(F){if(ft("Language definition for '{}' could not be registered.".replace("{}",w)),a)ft(F);else throw F;R=i}R.name||(R.name=w),e[w]=R,R.rawDefinition=k.bind(null,n),R.aliases&&Le(R.aliases,{languageName:w})}function X(w){delete e[w];for(let k of Object.keys(t))t[k]===w&&delete t[k]}function ae(){return Object.keys(e)}function ie(w){return w=(w||"").toLowerCase(),e[w]||e[t[w]]}function Le(w,{languageName:k}){typeof w=="string"&&(w=[w]),w.forEach(R=>{t[R.toLowerCase()]=k})}function ke(w){let k=ie(w);return k&&!k.disableAutodetect}function se(w){w["before:highlightBlock"]&&!w["before:highlightElement"]&&(w["before:highlightElement"]=k=>{w["before:highlightBlock"](Object.assign({block:k.el},k))}),w["after:highlightBlock"]&&!w["after:highlightElement"]&&(w["after:highlightElement"]=k=>{w["after:highlightBlock"](Object.assign({block:k.el},k))})}function ye(w){se(w),r.push(w)}function Be(w){let k=r.indexOf(w);k!==-1&&r.splice(k,1)}function Ne(w,k){let R=w;r.forEach(function(F){F[R]&&F[R](k)})}function Re(w){return zt("10.7.0","highlightBlock will be removed entirely in v12.0"),zt("10.7.0","Please use highlightElement now."),g(w)}Object.assign(n,{highlight:h,highlightAuto:_,highlightAll:P,highlightElement:g,highlightBlock:Re,configure:S,initHighlighting:M,initHighlightingOnLoad:D,registerLanguage:q,unregisterLanguage:X,listLanguages:ae,getLanguage:ie,registerAliases:Le,autoDetection:ke,inherit:Os,addPlugin:ye,removePlugin:Be}),n.debugMode=function(){a=!1},n.safeMode=function(){a=!0},n.versionString=Ac,n.regex={concat:mt,lookahead:zs,either:Ln,optional:jl,anyNumberOfTimes:Ul};for(let w in Nn)typeof Nn[w]=="object"&&Ds(Nn[w]);return Object.assign(n,Nn),n},Bt=qs({});Bt.newInstance=()=>qs({});Ks.exports=Bt;Bt.HighlightJS=Bt;Bt.default=Bt});var Da=`/*
 * World map: menus and search, the SVG map with its base map colors, zoom buttons, the
 * tooltip and coordinates under the pointer, the legend of values and the list of items.
 * Each base map sets the same --map-* colors; item colors are set through CSSOM.
 */
.map-body {
  display: grid;
  gap: var(--_space-2);
  padding: var(--_space-3);
  background: var(--_surface);
  font-family: var(--_font-ui);
  font-size: var(--_font-size-ui);
}

.map-muted,
.map-status {
  margin: 0;
  color: var(--_fg-muted);
  font-size: var(--_font-size-small);
}

.map-status:empty {
  display: none;
}

/* ---- menus and search ---- */
.map-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--_space-2) var(--_space-3);
}

.map-search {
  display: flex;
  flex: 1 1 16em;
  min-width: 0;
}

.map-search-input,
.map-select {
  min-width: 0;
  padding: 4px var(--_space-2);
  border: 1px solid var(--_border-strong);
  border-radius: var(--_radius-sm);
  background: var(--_surface);
  color: inherit;
  font: inherit;
}

.map-search-input {
  flex: 1;
  border-start-end-radius: 0;
  border-end-end-radius: 0;
}

.map-go {
  border: 1px solid var(--_border-strong);
  border-inline-start: 0;
  border-start-start-radius: 0;
  border-end-start-radius: 0;
}

.map-control,
.map-check {
  display: flex;
  align-items: center;
  gap: var(--_space-1);
}

.map-control label {
  color: var(--_fg-muted);
}

.map-search-input:focus-visible,
.map-select:focus-visible,
.map-check input:focus-visible,
.map-item-go:focus-visible,
.map-svg:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 2px;
}

/* ---- the map ---- */
.map-stage {
  --map-ocean: color-mix(in oklab, var(--_accent) 10%, var(--_surface));
  --map-ocean-edge: color-mix(in oklab, var(--_accent) 18%, var(--_surface));
  --map-land: var(--_surface-sunken, color-mix(in oklab, var(--_fg) 8%, var(--_surface)));
  --map-border: var(--_border-strong);
  --map-graticule: color-mix(in oklab, var(--_fg) 12%, transparent);
  --map-highlight: var(--_accent);
  --map-low: color-mix(in oklab, var(--_accent) 18%, var(--_surface));
  --map-high: var(--_accent);
  --map-pin: var(--_danger);
  --map-route: var(--_accent);
  --map-label: var(--_fg);
  --map-halo: var(--_surface);
  --map-space: transparent;
  --map-atmosphere: color-mix(in oklab, var(--_accent) 35%, transparent);

  position: relative;
  overflow: hidden;
  border: 1px solid var(--_border);
  border-radius: var(--_radius-sm);
  background: var(--map-space);
  aspect-ratio: 16 / 9;
  min-height: 200px;
  touch-action: none;
}

.map-stage > .loading,
.map-stage > .notice {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.map-svg {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
  user-select: none;
}

.map-svg.dragging {
  cursor: grabbing;
}

.map-sphere {
  stroke: var(--map-border);
  stroke-width: 0.5;
}

.ocean-a {
  stop-color: var(--map-ocean);
}

.ocean-b {
  stop-color: var(--map-ocean-edge);
}

.map-atmosphere {
  fill: var(--map-atmosphere);
  transform-box: fill-box;
  transform-origin: center;
  scale: 1.04;
}

.map-shading {
  pointer-events: none;
}

.shade-a {
  stop-color: #fff;
  stop-opacity: 0.18;
}

.shade-b {
  stop-color: #000;
  stop-opacity: 0;
}

.shade-c {
  stop-color: #000;
  stop-opacity: 0.35;
}

.map-graticule {
  fill: none;
  stroke: var(--map-graticule);
  stroke-width: 0.6;
  pointer-events: none;
}

.map-country {
  fill: var(--map-land);
  stroke: none;
  transition: fill var(--_duration-fast, 0.12s);
}

.map-stage[data-basemap] .map-country.highlighted {
  fill: var(--map-highlight);
}

.map-country.hover {
  filter: brightness(0.9);
}

.map-country.selected {
  stroke: var(--_fg);
  stroke-width: 1.6;
  paint-order: stroke;
}

.map-borders {
  fill: none;
  stroke: var(--map-border);
  stroke-width: 0.5;
  stroke-linejoin: round;
  pointer-events: none;
}

.map-shape {
  --map-item: var(--map-route);
  stroke: var(--map-item);
  stroke-width: 1.8;
  stroke-linejoin: round;
}

.map-shape.area {
  fill: color-mix(in oklab, var(--map-item) 30%, transparent);
}

.map-shape.line {
  fill: none;
}

.map-route {
  --map-item: var(--map-route);
  fill: none;
  stroke: var(--map-item);
  stroke-width: 2.2;
  stroke-dasharray: 7 4;
  stroke-linecap: round;
  pointer-events: none;
}

.map-pin {
  --map-item: var(--map-pin);
  cursor: pointer;
}

.map-pin.dropped {
  --map-item: var(--_fg);
}

.map-pin-shape {
  fill: var(--map-item);
  stroke: var(--map-halo);
  stroke-width: 1.5;
}

.map-pin-dot {
  fill: var(--map-halo);
}

.map-label,
.map-country-label {
  fill: var(--map-label);
  stroke: var(--map-halo);
  stroke-width: 3px;
  paint-order: stroke;
  font-family: var(--_font-ui);
  font-size: 13px;
  font-weight: 600;
  pointer-events: none;
}

.map-country-label {
  font-size: 11px;
  font-weight: 500;
}

.map-stars circle {
  fill: #fff;
}

.map-zoom {
  position: absolute;
  inset-block-start: var(--_space-2);
  inset-inline-end: var(--_space-2);
  display: grid;
  gap: 2px;
  border-radius: var(--_radius-sm);
  background: var(--_surface);
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.2);
}

.map-tooltip {
  position: absolute;
  z-index: 1;
  max-width: 16em;
  padding: 2px var(--_space-2);
  border: 1px solid var(--_border);
  border-radius: var(--_radius-sm);
  background: var(--_surface);
  color: var(--_fg);
  box-shadow: 0 2px 6px rgb(0 0 0 / 0.2);
  pointer-events: none;
  white-space: nowrap;
}

.map-tooltip[hidden] {
  display: none;
}

.map-readout {
  position: absolute;
  inset-block-end: var(--_space-1);
  inset-inline-start: var(--_space-2);
  padding: 0 var(--_space-1);
  border-radius: var(--_radius-sm);
  background: color-mix(in oklab, var(--_surface) 80%, transparent);
  color: var(--_fg);
  font-family: var(--_font-mono);
  font-size: var(--_font-size-small);
  pointer-events: none;
}

.map-readout:empty {
  display: none;
}

/* ---- base maps ---- */
.map-stage[data-basemap='dark'] {
  --map-ocean: #0f1b2b;
  --map-ocean-edge: #0a1320;
  --map-land: #2a3442;
  --map-border: #475569;
  --map-graticule: rgb(255 255 255 / 0.08);
  --map-highlight: #38bdf8;
  --map-low: #1e3a5f;
  --map-high: #38bdf8;
  --map-pin: #f43f5e;
  --map-route: #fbbf24;
  --map-label: #f1f5f9;
  --map-halo: #0f172a;
  --map-space: #0b1220;
}

.map-stage[data-basemap='political'] {
  --map-ocean: #cfe8f7;
  --map-ocean-edge: #b4d8ef;
  --map-border: #ffffff;
  --map-graticule: rgb(30 64 120 / 0.12);
  --map-highlight: #dc2626;
  --map-low: #fde68a;
  --map-high: #b91c1c;
  --map-pin: #111827;
  --map-route: #111827;
  --map-label: #111827;
  --map-halo: #ffffff;
}

.map-stage[data-basemap='political'] .c0 {
  fill: #f4c7a1;
}
.map-stage[data-basemap='political'] .c1 {
  fill: #c9e4a7;
}
.map-stage[data-basemap='political'] .c2 {
  fill: #f7e3a1;
}
.map-stage[data-basemap='political'] .c3 {
  fill: #d7c4ec;
}
.map-stage[data-basemap='political'] .c4 {
  fill: #f3b7c2;
}
.map-stage[data-basemap='political'] .c5 {
  fill: #b8dcd4;
}
.map-stage[data-basemap='political'] .c6 {
  fill: #e9d1b5;
}
.map-stage[data-basemap='political'] .c7 {
  fill: #c5d3ee;
}

.map-stage[data-basemap='satellite'] {
  --map-ocean: #1d4f80;
  --map-ocean-edge: #0c2748;
  --map-border: rgb(255 255 255 / 0.25);
  --map-graticule: rgb(255 255 255 / 0.1);
  --map-highlight: #facc15;
  --map-low: #fef08a;
  --map-high: #dc2626;
  --map-pin: #f43f5e;
  --map-route: #fde047;
  --map-label: #ffffff;
  --map-halo: #0b1a2c;
  --map-space: #050a14;
  --map-atmosphere: rgb(125 200 255 / 0.55);
}

.map-stage[data-basemap='satellite'] .ice {
  fill: #eef3f6;
}
.map-stage[data-basemap='satellite'] .tundra {
  fill: #7d8a6a;
}
.map-stage[data-basemap='satellite'] .forest {
  fill: #3f6b3a;
}
.map-stage[data-basemap='satellite'] .steppe {
  fill: #8f9256;
}
.map-stage[data-basemap='satellite'] .desert {
  fill: #c9a86a;
}
.map-stage[data-basemap='satellite'] .tropic {
  fill: #2f6d34;
}

.map-stage[data-basemap='night'] {
  --map-ocean: #030712;
  --map-ocean-edge: #020409;
  --map-land: #0b1324;
  --map-border: #22d3ee;
  --map-graticule: rgb(34 211 238 / 0.12);
  --map-highlight: #0e7490;
  --map-low: #083344;
  --map-high: #22d3ee;
  --map-pin: #f0abfc;
  --map-route: #f0abfc;
  --map-label: #e0f2fe;
  --map-halo: #020617;
  --map-space: #000000;
  --map-atmosphere: rgb(34 211 238 / 0.35);
}

.map-stage[data-basemap='blueprint'] {
  --map-ocean: #1e3a8a;
  --map-ocean-edge: #1e3a8a;
  --map-land: #2747a3;
  --map-border: #dbeafe;
  --map-graticule: rgb(219 234 254 / 0.25);
  --map-highlight: #60a5fa;
  --map-low: #3b5fc0;
  --map-high: #bfdbfe;
  --map-pin: #fde047;
  --map-route: #fde047;
  --map-label: #eff6ff;
  --map-halo: #1e3a8a;
  --map-space: #1e3a8a;
}

.map-stage[data-basemap='vintage'] {
  --map-ocean: #d9cfae;
  --map-ocean-edge: #c7b98f;
  --map-land: #efe4c4;
  --map-border: #8b6f47;
  --map-graticule: rgb(110 80 40 / 0.22);
  --map-highlight: #b45309;
  --map-low: #f5d9a8;
  --map-high: #9a3412;
  --map-pin: #7f1d1d;
  --map-route: #7f1d1d;
  --map-label: #3f2d14;
  --map-halo: #efe4c4;
  --map-space: #e8dcb8;
}

.map-stage[data-basemap='mono'] {
  --map-ocean: var(--_surface);
  --map-ocean-edge: var(--_surface);
  --map-land: color-mix(in oklab, var(--_fg) 14%, var(--_surface));
  --map-border: var(--_surface);
  --map-highlight: var(--_fg);
  --map-low: color-mix(in oklab, var(--_fg) 20%, var(--_surface));
  --map-high: var(--_fg);
  --map-pin: var(--_fg);
  --map-route: var(--_fg);
}

/* ---- legend and list ---- */
.map-legend {
  display: flex;
  align-items: center;
  gap: var(--_space-2);
  font-size: var(--_font-size-small);
}

.map-legend-bar {
  flex: 0 1 14em;
  height: 10px;
  border-radius: var(--_radius-full);
  background: linear-gradient(
    to right,
    var(--map-low, var(--_accent-soft)),
    var(--map-high, var(--_accent))
  );
}

.map-legend-host:empty,
.map-list-host:empty {
  display: none;
}

.map-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15em, 1fr));
  gap: 2px var(--_space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.map-item {
  display: flex;
  align-items: center;
  gap: var(--_space-2);
  min-width: 0;
}

.map-item.pending {
  color: var(--_fg-muted);
}

.map-swatch {
  --map-item: var(--_danger);
  flex: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--map-item);
}

.map-swatch.country {
  --map-item: var(--_accent);
  border-radius: 2px;
}

.map-swatch.route,
.map-swatch.shape {
  --map-item: var(--_accent);
  height: 3px;
  border-radius: 0;
}

.map-swatch.pin {
  --map-item: var(--_fg);
}

.map-item-go,
.map-item-name {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-item-go {
  padding: 2px 0;
  border: 0;
  background: none;
  color: var(--_accent-fg);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.map-item-go:hover {
  text-decoration: underline;
}

.map-item-note {
  margin-inline-start: auto;
  color: var(--_fg-muted);
  font-family: var(--_font-mono);
  font-size: var(--_font-size-small);
  white-space: nowrap;
}

.map-edit {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
}

@media (max-width: 640px) {
  .map-edit {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-country {
    transition: none;
  }
}

/* ---- film sequence: a surveillance screen over the map ---- */
.map-stage.movie .map-zoom,
.map-stage.movie .map-readout,
.map-stage.movie .map-tooltip,
.map-stage.movie .map-labels {
  display: none;
}

.map-stage.movie .map-svg {
  filter: saturate(0.75) contrast(1.15);
  pointer-events: none;
}

.map-hud {
  --hud: #5eead4;
  --hud-alert: #ff2d2d;
  position: absolute;
  inset: 0;
  z-index: 2;
  overflow: hidden;
  color: var(--hud);
  font-family: var(--_font-mono);
  font-size: clamp(10px, 1.4vw, 13px);
  letter-spacing: 0.08em;
  text-shadow: 0 0 6px color-mix(in oklab, var(--hud) 60%, transparent);
  background: radial-gradient(ellipse at center, transparent 55%, rgb(0 0 0 / 0.55) 100%);
  pointer-events: none;
}

.hud-scan {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    to bottom,
    rgb(255 255 255 / 0.05) 0 1px,
    transparent 1px 3px
  );
  mix-blend-mode: overlay;
}

.hud-scan::after {
  content: '';
  position: absolute;
  inset-inline: 0;
  height: 18%;
  background: linear-gradient(
    to bottom,
    transparent,
    color-mix(in oklab, var(--hud) 14%, transparent),
    transparent
  );
  animation: hud-sweep 3s linear infinite;
}

.hud-corners {
  position: absolute;
  inset: 12px;
  background:
    linear-gradient(var(--hud), var(--hud)) top left / 28px 2px,
    linear-gradient(var(--hud), var(--hud)) top left / 2px 28px,
    linear-gradient(var(--hud), var(--hud)) top right / 28px 2px,
    linear-gradient(var(--hud), var(--hud)) top right / 2px 28px,
    linear-gradient(var(--hud), var(--hud)) bottom left / 28px 2px,
    linear-gradient(var(--hud), var(--hud)) bottom left / 2px 28px,
    linear-gradient(var(--hud), var(--hud)) bottom right / 28px 2px,
    linear-gradient(var(--hud), var(--hud)) bottom right / 2px 28px;
  background-repeat: no-repeat;
  opacity: 0.8;
}

.hud-reticle {
  position: absolute;
  inset-block-start: 50%;
  inset-inline-start: 50%;
  width: 26%;
  aspect-ratio: 1;
  translate: -50% -50%;
}

.hud-reticle::before,
.hud-reticle::after {
  content: '';
  position: absolute;
  background: var(--hud);
  opacity: 0.7;
}

.hud-reticle::before {
  inset-block: -30% -30%;
  inset-inline-start: 50%;
  width: 1px;
}

.hud-reticle::after {
  inset-inline: -30% -30%;
  inset-block-start: 50%;
  height: 1px;
}

.hud-ring {
  position: absolute;
  inset: 0;
  border: 1px dashed var(--hud);
  border-radius: 50%;
  animation: hud-spin 8s linear infinite;
}

.hud-box {
  position: absolute;
  inset: 34%;
  border: 2px solid var(--hud);
  transition:
    inset 0.6s var(--_easing, ease),
    border-color 0.3s;
}

.hud-top {
  position: absolute;
  inset-block-start: 22px;
  inset-inline: 28px;
  display: flex;
  justify-content: space-between;
  gap: 1em;
}

.hud-rec {
  color: var(--hud-alert);
  text-shadow: 0 0 6px var(--hud-alert);
  animation: hud-blink 1s steps(2, start) infinite;
}

.hud-rec::before {
  content: '\u25CF ';
}

.hud-log {
  position: absolute;
  inset-block-end: 26px;
  inset-inline-start: 28px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.hud-log li:last-child::after {
  content: '\u258C';
  animation: hud-blink 0.8s steps(2, start) infinite;
}

.hud-coords {
  position: absolute;
  inset-block-end: 26px;
  inset-inline-end: 28px;
  font-size: 1.15em;
  font-variant-numeric: tabular-nums;
}

.hud-locked {
  position: absolute;
  inset-block-start: 50%;
  inset-inline: 0;
  translate: 0 -260%;
  text-align: center;
  opacity: 0;
}

.hud-locked strong {
  display: inline-block;
  padding: 0.3em 0.9em;
  border: 2px solid var(--hud-alert);
  background: rgb(60 0 0 / 0.55);
  color: var(--hud-alert);
  font-size: clamp(16px, 3.4vw, 34px);
  font-weight: 800;
  letter-spacing: 0.25em;
  text-shadow: 0 0 12px var(--hud-alert);
  box-shadow:
    0 0 24px rgb(255 45 45 / 0.45),
    inset 0 0 18px rgb(255 45 45 / 0.35);
}

.map-hud.locked .hud-locked {
  opacity: 1;
  animation:
    hud-lock 0.9s ease-out both,
    hud-pulse 1.2s ease-in-out 0.9s infinite;
}

.map-hud.locked .hud-box {
  inset: 42%;
  border-color: var(--hud-alert);
  box-shadow: 0 0 14px var(--hud-alert);
}

.map-hud.locked .hud-coords,
.map-hud.locked .hud-log li:last-child {
  color: var(--hud-alert);
  text-shadow: 0 0 8px var(--hud-alert);
}

.hud-stop {
  position: absolute;
  inset-block-start: 48px;
  inset-inline-end: 28px;
  padding: 2px 10px;
  border: 1px solid var(--hud);
  border-radius: 2px;
  background: rgb(0 0 0 / 0.5);
  color: var(--hud);
  font: inherit;
  letter-spacing: inherit;
  text-transform: uppercase;
  cursor: pointer;
  pointer-events: auto;
}

.hud-stop:focus-visible {
  outline: 2px solid var(--hud);
  outline-offset: 2px;
}

@keyframes hud-sweep {
  from {
    translate: 0 -100%;
  }
  to {
    translate: 0 600%;
  }
}

@keyframes hud-pulse {
  50% {
    opacity: 0.55;
  }
}

@keyframes hud-spin {
  to {
    rotate: 360deg;
  }
}

@keyframes hud-blink {
  to {
    visibility: hidden;
  }
}

@keyframes hud-lock {
  from {
    opacity: 0;
    scale: 1.8;
    filter: blur(6px);
  }
  to {
    opacity: 1;
    scale: 1;
    filter: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hud-scan::after,
  .hud-ring,
  .hud-rec,
  .hud-log li:last-child::after,
  .map-hud.locked .hud-locked {
    animation: none;
  }
}
`;function Ie(n){if(n===null)return null;let e=n.trim().toLowerCase();return!(e==="false"||e==="off"||e==="no"||e==="0")}function Rt(n,{min:e,max:t,fallback:r}){if(n===null||n.length>32)return r;let a=n.trim();if(!/^[+-]?\d+$/.test(a))return r;let s=Number(a);return Number.isSafeInteger(s)?Math.min(t,Math.max(e,s)):r}function Ot(n,e,t){if(n===null)return t;let r=n.trim().toLowerCase();return e.includes(r)?r:t}var Xo=500;function fr(n){if(!n||n.length>1e3*10)return[];let e=[];for(let r of n.split(",")){if(e.length>=Xo)break;let a=/^\s*(\d{1,9})\s*(?:-\s*(\d{1,9})\s*)?$/.exec(r);if(!a)continue;let s=Number(a[1]),i=a[2]===void 0?s:Number(a[2]);e.push([Math.min(s,i),Math.max(s,i)])}e.sort((r,a)=>r[0]-a[0]);let t=[];for(let r of e){let a=t[t.length-1];a&&r[0]<=a[1]+1?a[1]=Math.max(a[1],r[1]):t.push([r[0],r[1]])}return t}function Pa(n,e){let t=0,r=e.length-1;for(;t<=r;){let a=t+r>>1,[s,i]=e[a];if(n<s)r=a-1;else if(n>i)t=a+1;else return!0}return!1}function za(n){if(n===null)return null;let e=n.trim().toLowerCase();return/^\d{1,6}(?:\.\d{1,4})?(?:px|em|rem|vh|svh|lvh|dvh|%|ch|lh)$/.test(e)?e:null}function Ba(n,e=200){if(!n)return"";let r=n.slice(0,e*4).replace(/[\u0000-\u001f\u007f-\u009f]/g,"").replace(/\s+/g," ").trim();return r.length>e?r.slice(0,e-1)+"\u2026":r}function Ua(n,e){let t=(n??"").split(/[\\/]/).pop()??"",r=/[\u0000-\u001f\u007f<>:"|?*]/g;return t.replace(r,"").replace(/^[.\s]+/,"").trim().slice(0,120)||e}var ja=`/*
 * Theme-independent tokens: typography, spacing, radius, motion.
 * Values: docs/DESIGN_SYSTEM.md \xA73, \xA74 and \xA77.
 * Each private \`--_\` variable reads the public \`--vt-\` variable first, so hosts can
 * override any token on the element or on an ancestor.
 */
:host {
  --_font-ui: var(
    --vt-font-ui,
    system-ui,
    -apple-system,
    'Segoe UI',
    'IBM Plex Sans',
    Roboto,
    sans-serif
  );
  --_font-mono: var(
    --vt-font-mono,
    'JetBrains Mono',
    ui-monospace,
    'Cascadia Code',
    'SF Mono',
    Menlo,
    Consolas,
    monospace
  );
  --_font-size: var(--vt-font-size, 14px);
  --_font-size-small: var(--vt-font-size-small, 12px);
  --_font-size-ui: var(--vt-font-size-ui, 13px);
  --_line-height: var(--vt-line-height, 1.6);
  --_space-1: var(--vt-space-1, 4px);
  --_space-2: var(--vt-space-2, 8px);
  --_space-3: var(--vt-space-3, 12px);
  --_space-4: var(--vt-space-4, 16px);
  --_space-5: var(--vt-space-5, 24px);
  --_space-6: var(--vt-space-6, 32px);
  --_space-7: var(--vt-space-7, 48px);
  --_space-8: var(--vt-space-8, 64px);
  --_radius-sm: var(--vt-radius-sm, 6px);
  --_radius: var(--vt-radius, 10px);
  --_radius-lg: var(--vt-radius-lg, 16px);
  --_radius-full: var(--vt-radius-full, 999px);
  --_header-height: var(--vt-header-height, 40px);
  --_tab-size: var(--vt-tab-size, 4);
  --_duration-fast: var(--vt-duration-fast, 120ms);
  --_duration: var(--vt-duration, 180ms);
  --_easing: var(--vt-easing, cubic-bezier(0.2, 0, 0, 1));
}

@media (prefers-reduced-motion: reduce) {
  :host {
    --_duration-fast: 0ms;
    --_duration: 0ms;
  }
}
`;var Fa=`/*
 * Shared component frame: container, header, toolbar, tabs, search, states.
 * Anatomy: docs/DESIGN_SYSTEM.md \xA76. Colors come only from theme tokens.
 */
:host {
  display: block;
  min-width: 0;
  margin-block: var(--vt-margin, 0);
}

:host([hidden]) {
  display: none;
}

[hidden] {
  display: none !important;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

.vt {
  /* Code areas: interface colors by default, replaced by a syntax theme when one is set. */
  --_code-bg: var(--_surface-sunken);
  --_code-bg-solid: var(--_surface-sunken);
  --_code-fg: var(--_fg);
  --_code-gutter: color-mix(in srgb, var(--_fg-muted) 70%, transparent);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  color: var(--_fg);
  background: var(--_surface);
  border: 1px solid var(--_border);
  border-radius: var(--_radius);
  font-family: var(--_font-ui);
  font-size: var(--_font-size-ui);
  line-height: 1.4;
  text-align: start;
  -webkit-text-size-adjust: 100%;
}

/* Chrome always uses the UI font, even when the content inherits the page font. */
.header,
.search,
.notice,
.message,
.empty,
.more,
.toolbar,
.toc {
  font-family: var(--_font-ui);
  font-size: var(--_font-size-ui);
  line-height: 1.4;
}

/* ---------- Header ---------- */

.header {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--_space-2);
  min-height: var(--_header-height);
  padding: 0 var(--_space-2) 0 var(--_space-3);
  border-bottom: 1px solid var(--_border);
  background: var(--_surface);
}

.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: var(--_radius-full);
  background: var(--_accent);
}

.title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  color: var(--_fg);
  font-weight: 500;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.spacer {
  flex: 1 1 auto;
}

.badge {
  flex: none;
  padding: 2px 6px;
  border-radius: var(--_radius-sm);
  background: var(--_surface-sunken);
  color: var(--_fg-muted);
  font-size: var(--_font-size-small);
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
}

.vt {
  position: relative;
}

.toolbar {
  display: flex;
  flex: none;
  align-items: center;
  gap: 2px;
}

.toolbar.floating {
  position: absolute;
  top: var(--_space-2);
  right: var(--_space-2);
  z-index: 3;
  padding: 2px;
  border: 1px solid var(--_border);
  border-radius: var(--_radius-sm);
  background: var(--_surface);
  opacity: 0;
  transition: opacity var(--_duration-fast) var(--_easing);
}

.vt:hover .toolbar.floating,
.toolbar.floating:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .toolbar.floating {
    opacity: 1;
  }
}

/* ---------- Buttons ---------- */

.btn {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--_radius-sm);
  background: transparent;
  color: var(--_fg-muted);
  font: inherit;
  cursor: pointer;
  transition:
    background-color var(--_duration-fast) var(--_easing),
    color var(--_duration-fast) var(--_easing);
}

.btn:hover {
  background: var(--_accent-soft);
  color: var(--_fg);
}

.btn[aria-pressed='true'] {
  background: var(--_accent-soft);
  color: var(--_accent-fg);
}

.btn.done {
  color: var(--_success);
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
  background: transparent;
}

.icon {
  width: 16px;
  height: 16px;
  pointer-events: none;
}

.text-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--_space-1);
  min-height: 28px;
  padding: 0 var(--_space-2);
  border: 1px solid var(--_border-strong);
  border-radius: var(--_radius-sm);
  background: var(--_surface);
  color: var(--_fg);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  transition: background-color var(--_duration-fast) var(--_easing);
}

.text-btn:hover {
  background: var(--_accent-soft);
}

.text-btn.done {
  border-color: var(--_success);
  color: var(--_success);
}

.pathbar .text-btn {
  min-height: 24px;
  font-size: var(--_font-size-small);
}

:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 2px;
}

:focus:not(:focus-visible) {
  outline: none;
}

@media (pointer: coarse) {
  .btn {
    width: 44px;
    height: 44px;
  }

  .text-btn,
  .tab {
    min-height: 44px;
  }
}

/* ---------- Tabs (WAI-ARIA tabs pattern) ---------- */

.tabs {
  display: flex;
  align-self: stretch;
  align-items: stretch;
  gap: var(--_space-1);
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 var(--_space-2);
  border: 0;
  background: transparent;
  color: var(--_fg-muted);
  font: inherit;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--_duration-fast) var(--_easing);
}

.tab::after {
  content: '';
  position: absolute;
  right: var(--_space-2);
  bottom: -1px;
  left: var(--_space-2);
  height: 2px;
  border-radius: 2px;
  background: transparent;
  transition: background-color var(--_duration) var(--_easing);
}

.tab:hover {
  color: var(--_fg);
}

.tab[aria-selected='true'] {
  color: var(--_fg);
}

.tab[aria-selected='true']::after {
  background: var(--_accent);
}

.tab:focus-visible {
  outline-offset: -2px;
}

.tab .icon {
  width: 14px;
  height: 14px;
}

/* ---------- Search ---------- */

.search {
  display: flex;
  align-items: center;
  gap: var(--_space-1);
  padding: var(--_space-2) var(--_space-2) var(--_space-2) var(--_space-3);
  border-bottom: 1px solid var(--_border);
  background: var(--_surface);
}

.search-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 28px;
  padding: 0 var(--_space-2);
  border: 1px solid var(--_border-strong);
  border-radius: var(--_radius-sm);
  background: var(--_surface-sunken);
  color: var(--_fg);
  font: inherit;
}

.search-input::placeholder {
  color: var(--_fg-muted);
  opacity: 1;
}

.search-input:focus-visible {
  outline-offset: 0;
  border-color: var(--_accent);
}

.search-count {
  flex: none;
  min-width: 5ch;
  color: var(--_fg-muted);
  font-variant-numeric: tabular-nums;
  text-align: end;
  white-space: nowrap;
}

mark.match {
  border-radius: 2px;
  background: var(--_highlight);
  color: inherit;
}

mark.match.current {
  background: var(--_highlight-current);
  box-shadow: 0 0 0 1px var(--_warning);
}

/* ---------- Body ---------- */

.body {
  position: relative;
  min-width: 0;
  max-height: var(--_max-height, none);
  overflow: auto;
  background: var(--_code-bg);
  /*
   * Without a height limit the page must keep scrolling: a body that only scrolls
   * sideways (long lines) would otherwise swallow vertical wheel and touch scrolling.
   */
  overscroll-behavior: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--_border-strong) transparent;
}

:host([max-height]) .body,
.vt[data-fullscreen] .body {
  overscroll-behavior: contain;
}

.body:focus-visible {
  outline-offset: -2px;
}

/* ---------- States ---------- */

.notice {
  display: flex;
  align-items: center;
  gap: var(--_space-2);
  padding: var(--_space-2) var(--_space-3);
  border-bottom: 1px solid var(--_border);
  background: var(--_surface);
  color: var(--_fg-muted);
  font-size: var(--_font-size-small);
}

.notice .icon {
  flex: none;
  width: 14px;
  height: 14px;
  color: var(--_warning);
}

.message {
  display: flex;
  align-items: flex-start;
  gap: var(--_space-2);
  padding: var(--_space-4);
  background: var(--_surface);
  overflow-wrap: anywhere;
}

.message .icon {
  flex: none;
  margin-top: 1px;
  color: var(--_danger);
}

.message-title {
  margin: 0;
  color: var(--_danger);
  font-weight: 600;
}

.message-detail {
  margin: var(--_space-1) 0 0;
  color: var(--_fg-muted);
}

.empty {
  padding: var(--_space-5) var(--_space-4);
  color: var(--_fg-muted);
  text-align: center;
}

.loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--_space-3);
  min-height: 140px;
  padding: var(--_space-5);
  color: var(--_fg-muted);
  /* Fast loads show nothing: the loader only appears after a short delay. */
  opacity: 0;
  animation: vt-loader-in var(--_duration) var(--_easing) 300ms forwards;
}

.loader-mark {
  width: 44px;
  height: 44px;
  overflow: visible;
}

.loader-frame {
  fill: none;
  stroke: currentColor;
  stroke-width: 9;
}

.loader-dot {
  fill: var(--_accent);
  transform-origin: 29px 29px;
  animation: vt-loader-dot 1.4s var(--_easing) infinite;
}

.loader-v {
  fill: none;
  stroke: var(--_accent);
  stroke-width: 11;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  animation: vt-loader-v 1.4s var(--_easing) infinite;
}

.loader-label {
  font-size: var(--_font-size-small);
}

@keyframes vt-loader-in {
  to {
    opacity: 1;
  }
}

@keyframes vt-loader-v {
  0% {
    stroke-dashoffset: 100;
  }
  45%,
  70% {
    stroke-dashoffset: 0;
  }
  100% {
    stroke-dashoffset: -100;
  }
}

@keyframes vt-loader-dot {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .loader {
    animation-duration: 0ms;
  }

  .loader-v,
  .loader-dot {
    animation: none;
    stroke-dashoffset: 0;
    opacity: 1;
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

/* ---------- Full screen ---------- */

:host(:fullscreen) {
  display: block;
  width: 100%;
  height: 100%;
}

.vt[data-fullscreen] {
  height: 100%;
  border-radius: 0;
  border-width: 0;
}

/* Window mode: used where the Fullscreen API is not available. */
.vt[data-fullscreen='window'] {
  position: fixed;
  inset: 0;
  z-index: 2147483000;
  height: auto;
}

.vt[data-fullscreen] > .panel,
.vt[data-fullscreen] > .body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.vt[data-fullscreen] .body {
  flex: 1 1 auto;
  max-height: none;
}

.vt[data-fullscreen] .panel.split {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}

.vt[data-fullscreen] .panel.split:is([data-preview='top'], [data-preview='bottom']) {
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
}

.vt[data-fullscreen] .panel.split > .body {
  height: auto;
  min-height: 0;
}
`;var tt=`/*
 * Syntax highlighting roles for highlight.js classes.
 * Mapping: docs/DESIGN_SYSTEM.md \xA72.3. Colors come from theme tokens.
 */
.hljs-keyword,
.hljs-built_in,
.hljs-literal,
.hljs-bullet,
.hljs-doctag {
  color: var(--_syntax-keyword);
}

.hljs-string,
.hljs-regexp,
.hljs-symbol,
.hljs-char,
.hljs-code,
.hljs-link {
  color: var(--_syntax-string);
}

.hljs-number {
  color: var(--_syntax-number);
}

.hljs-title,
.hljs-title.function_,
.hljs-section,
.hljs-selector-class,
.hljs-selector-id {
  color: var(--_syntax-function);
}

.hljs-type,
.hljs-title.class_,
.hljs-title.class_.inherited__ {
  color: var(--_syntax-type);
}

.hljs-comment,
.hljs-quote {
  color: var(--_syntax-comment);
  font-style: italic;
}

.hljs-attr,
.hljs-attribute,
.hljs-property,
.hljs-template-variable,
.hljs-variable.language_ {
  color: var(--_syntax-attr);
}

.hljs-tag,
.hljs-name,
.hljs-selector-tag,
.hljs-selector-pseudo,
.hljs-selector-attr {
  color: var(--_syntax-tag);
}

.hljs-meta,
.hljs-punctuation,
.hljs-operator,
.hljs-tag .hljs-punctuation {
  color: var(--_syntax-meta);
}

.hljs-meta .hljs-keyword {
  color: var(--_syntax-keyword);
}

.hljs-meta .hljs-string {
  color: var(--_syntax-string);
}

.hljs-addition {
  color: var(--_success);
}

.hljs-deletion {
  color: var(--_danger);
}

.hljs-section,
.hljs-strong {
  font-weight: 600;
}

.hljs-emphasis {
  font-style: italic;
}

.hljs-link {
  text-decoration: underline;
  text-underline-offset: 3px;
}
`;async function mr(n,e=document){if(navigator.clipboard&&window.isSecureContext)try{return await navigator.clipboard.writeText(n),!0}catch{}return nl(n,e)}function nl(n,e){let t=document.createElement("textarea");t.value=n,t.setAttribute("readonly",""),t.setAttribute("aria-hidden","true"),t.style.position="fixed",t.style.opacity="0",t.style.pointerEvents="none",(e instanceof Document?e.body:e).appendChild(t);try{return t.select(),document.execCommand("copy")}catch{return!1}finally{t.remove()}}function $a(n,e,t="text/plain"){let r=new Blob([n],{type:`${t};charset=utf-8`}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=e,s.rel="noopener",s.style.display="none",document.body.appendChild(s),s.click(),s.remove(),setTimeout(()=>URL.revokeObjectURL(a),1e3)}var gr=Object.freeze({theme:"auto",lightTheme:"light",darkTheme:"dark",lang:"en",maxSize:2097152,highlightLimit:3e5,maxDepth:512,fetchTimeout:15e3,languagesUrl:"",syntaxTheme:"",syntaxThemeDark:"",syntaxThemesUrl:"",vendorUrl:""}),rl=Object.freeze({maxSize:50*1024*1024,highlightLimit:5*1024*1024,maxDepth:1e4,fetchTimeout:12e4}),It={...gr},br=new Set;function W(){return Object.freeze({...It})}function Ha(n){if(!n||typeof n!="object")return W();let e={...It};for(let[r,a]of Object.entries(n))al(r,a);let t=new Set(Object.keys(It).filter(r=>It[r]!==e[r]));if(t.size)for(let r of br)r(t);return W()}function al(n,e){if(!Object.prototype.hasOwnProperty.call(gr,n)){console.warn(`[vitrine] Unknown configuration option "${n}".`);return}let t=n;if(typeof gr[t]==="number"){let a=rl[t];if(typeof e!="number"||!Number.isFinite(e)||e<=0){console.warn(`[vitrine] Option "${n}" must be a positive number.`);return}It[t]=Math.min(Math.floor(e),a??e);return}if(typeof e!="string"||e.length>2048){console.warn(`[vitrine] Option "${n}" must be a string.`);return}It[t]=e.trim()}function Ga(n){return br.add(n),()=>br.delete(n)}function f(n,e={},...t){let r=document.createElement(n);if(e.class&&(r.className=e.class),e.part&&r.setAttribute("part",e.part),e.attrs)for(let[a,s]of Object.entries(e.attrs))s===!1||s===null||s===void 0||r.setAttribute(a,s===!0?"":String(s));if(e.text!==void 0&&(r.textContent=e.text),e.on)for(let[a,s]of Object.entries(e.on))r.addEventListener(a,s);return sl(r,t),r}function sl(n,e){for(let t of e)t==null||t===!1||n.append(typeof t=="string"?document.createTextNode(t):t)}var Va=0;function _e(n){return Va+=1,`vt-${n}-${Va}`}function _n(n){let e=n.replace(/\r\n?/g,`
`).split(`
`);for(;e.length&&e[0].trim()==="";)e.shift();for(;e.length&&e[e.length-1].trim()==="";)e.pop();let t=1/0;for(let r of e){if(r.trim()==="")continue;let a=/^[ \t]*/.exec(r);if(t=Math.min(t,a?a[0].length:0),t===0)break}return!Number.isFinite(t)||t===0?e.join(`
`):e.map(r=>r.slice(t)).join(`
`)}function qa(n,e){let t,r=(...a)=>{clearTimeout(t),t=setTimeout(()=>n(...a),e)};return r.cancel=()=>clearTimeout(t),r}var il=new Set(["http:","https:","mailto:","tel:"]),ol=/^data:image\/(?:png|gif|jpe?g|webp|avif);base64,[a-z0-9+/]+=*$/i;function Ka(n,e={}){if(typeof n!="string")return!1;let t=0,r=n.length;for(;t<r&&n.charCodeAt(t)<=32;)t+=1;for(;r>t&&n.charCodeAt(r-1)<=32;)r-=1;let a=n.slice(t,r).replace(/[\t\n\r]/g,"");if(a===""||e.allowDataImage&&ol.test(a))return!0;let s=/^([a-z][a-z0-9+.-]*):/i.exec(a);return s?il.has(s[1].toLowerCase()+":"):!0}function Wa(n){try{return new URL(n,document.baseURI).origin===location.origin}catch{return!1}}var ue=class extends Error{constructor(e,t={},r){super(e,r===void 0?void 0:{cause:r}),this.name="VitrineError",this.code=e,this.params=t}},ll=new Set(["text/plain","text/markdown","text/x-markdown","application/json","text/json","application/xml","text/xml"]);function Ya(n){for(let r of Array.from(n.children)){if(r.hasAttribute("data-json"))continue;let a=cl(r);if(a!==null)return a}let e="";for(let r of Array.from(n.childNodes))r.nodeType===Node.TEXT_NODE||r.nodeType===Node.CDATA_SECTION_NODE?e+=r.nodeValue??"":r.nodeType===Node.ELEMENT_NODE&&!r.hasAttribute("data-json")&&(e+=r.textContent??"");let t=_n(e);return t===""?null:t}function cl(n){if(n instanceof HTMLTemplateElement){let e=n.content.children.length>0;return _n(e?n.innerHTML:n.content.textContent??"")}return n instanceof HTMLScriptElement&&ll.has(n.type.trim().toLowerCase())?_n(n.textContent??""):null}function Kt(n,e){if(n.length>e)throw new ue("tooLarge",{size:n.length,limit:e})}async function yr(n,e){let t=ul(n),r=Wa(t.href);if(!r&&!e.allowRemote)throw new ue("remoteBlocked");let a=new AbortController,s=setTimeout(()=>a.abort(new ue("timeout")),e.timeout),i=()=>a.abort(e.signal?.reason);e.signal?.addEventListener("abort",i,{once:!0}),e.signal?.aborted&&i();try{let o=await fetch(t.href,{mode:r?"same-origin":"cors",credentials:"same-origin",redirect:"follow",referrerPolicy:"strict-origin-when-cross-origin",signal:a.signal});if(!o.ok)throw new ue("loadFailed",{url:Za(t),reason:`HTTP ${o.status}`});let c=Number(o.headers.get("content-length"));if(Number.isFinite(c)&&c>e.maxSize*4)throw new ue("tooLarge",{size:c,limit:e.maxSize});return await dl(o,e.maxSize,a)}catch(o){throw hl(o,a.signal,t)}finally{clearTimeout(s),e.signal?.removeEventListener("abort",i)}}function ul(n){let e;try{e=new URL(n.trim(),document.baseURI)}catch{throw new ue("unsafeUrl")}if(e.protocol!=="http:"&&e.protocol!=="https:")throw new ue("unsafeUrl");return e}async function dl(n,e,t){if(!n.body){let i=await n.text();return Kt(i,e),i}let r=n.body.getReader(),a=new TextDecoder,s="";for(;;){let{done:i,value:o}=await r.read();if(i)break;if(s+=a.decode(o,{stream:!0}),s.length>e)throw t.abort(),new ue("tooLarge",{size:`> ${e}`,limit:e})}return s+=a.decode(),Kt(s,e),s}function hl(n,e,t){if(n instanceof ue)return n;if(e.aborted&&e.reason instanceof ue)return e.reason;if(n instanceof DOMException&&n.name==="AbortError")return n;let r=n instanceof Error?n.message:String(n);return new ue("loadFailed",{url:Za(t),reason:r},n)}function Za(n){let e=n.origin===location.origin?n.pathname+n.search:n.href;return e.length>120?e.slice(0,119)+"\u2026":e}function vr(n){return n instanceof DOMException&&n.name==="AbortError"}var pl=1e3,qe=n=>typeof n=="object"&&n!==null&&!Array.isArray(n);function De(n,e=4e3){return typeof n=="number"&&Number.isFinite(n)?String(n):typeof n=="string"?n.trim().slice(0,e):""}function xr(n,e,t){for(let r of e){let a=De(n[r],t);if(a)return a}return""}function Ja(n){let e=De(n,2e3);return e&&Ka(e)?e:null}function Dt(n){if(typeof n=="number")return Number.isFinite(n)?n:null;if(typeof n!="string"||!n.trim())return null;let e=Number(n);return Number.isFinite(e)?e:null}function Xa(n,e){let t;try{t=JSON.parse(n)}catch(a){return{ok:!1,error:"json",message:a instanceof Error?a.message:""}}let r=t;return qe(t)&&(r=e.map(a=>t[a]).find(Array.isArray)),Array.isArray(r)?{ok:!0,items:r.filter(qe).slice(0,pl),root:qe(t)?t:{}}:{ok:!1,error:"shape",message:e.map(a=>`"${a}"`).join(", ")}}function Qa(n,e){let t=e.replace(/\[(\d+)\]/g,".$1").split(".").map(a=>a.trim()).filter(Boolean),r=n;for(let a of t.slice(0,32))if(Array.isArray(r)&&/^\d+$/.test(a)&&Number(a)<r.length)r=r[Number(a)];else if(qe(r)&&Object.hasOwn(r,a))r=r[a];else return{ok:!1};return{ok:!0,value:r}}function Wt(n){return JSON.stringify(n===void 0?null:n,null,2)??"null"}function es(n,{keys:e,attributes:t={},otherwise:r}){if(typeof n=="string")return{content:n};if(qe(n)){let a=e.find(s=>typeof n[s]=="string");if(a!==void 0){let s={};for(let[i,o]of Object.entries(t))Object.hasOwn(n,i)&&!Object.hasOwn(s,o)&&(s[o]=n[i]);return{content:n[a],attributes:s}}}return r?r(n):{content:Wt(n)}}var te=Object.freeze({READY:"vt-ready",COPY:"vt-copy",SEARCH:"vt-search",TAB_CHANGE:"vt-tab-change",INPUT:"vt-input",CHANGE:"vt-change",MODE_CHANGE:"vt-mode-change",TAG_ADD:"vt-tag-add",TAG_REMOVE:"vt-tag-remove",TAG_CREATE:"vt-tag-create",TAG_CLICK:"vt-tag-click",SORT:"vt-sort",FULLSCREEN_CHANGE:"vt-fullscreen-change",LAYOUT_CHANGE:"vt-layout-change",SELECT:"vt-select",TOGGLE:"vt-toggle",FILTER_CHANGE:"vt-filter-change",TYPING_END:"vt-typing-end",CHANGE_NAVIGATE:"vt-change-navigate",STEP_TOGGLE:"vt-step-toggle",JOB_CHANGE:"vt-job-change",MATCH:"vt-match",BULK_ACTION:"vt-bulk-action",CELL_EDIT:"vt-cell-edit",COLUMN_CHANGE:"vt-column-change",ROW_ACTIVATE:"vt-row-activate",STATUS_CHANGE:"vt-status-change",DATE_CHANGE:"vt-date-change",EVENT_SELECT:"vt-event-select",PRICING_CHANGE:"vt-pricing-change",PLAN_SELECT:"vt-plan-select",TASK_ADD:"vt-task-add",TASK_MOVE:"vt-task-move",TASK_EDIT:"vt-task-edit",TASK_DELETE:"vt-task-delete",COUNTDOWN_END:"vt-countdown-end",FILE_ADD:"vt-file-add",FILE_REMOVE:"vt-file-remove",UPLOAD_START:"vt-upload-start",UPLOAD_PROGRESS:"vt-upload-progress",UPLOAD_DONE:"vt-upload-done",UPLOAD_ERROR:"vt-upload-error",DOWNLOAD:"vt-download",GENERATE:"vt-generate",BREACH:"vt-breach",ROTATE:"vt-rotate",CONSENT:"vt-consent",HASH:"vt-hash",VERIFY:"vt-verify",LOADING_START:"vt-loading-start",LOADING_END:"vt-loading-end",PROGRESS:"vt-progress",COMPLETE:"vt-complete",CANCEL:"vt-cancel",ERROR:"vt-error"});function ne(n,e,t){return n.dispatchEvent(new CustomEvent(e,{detail:t,bubbles:!0,composed:!0,cancelable:!0}))}var ns=Object.freeze({copy:"Copy",copyCode:"Copy code",copied:"Copied",copyFailed:"Copy failed",copySource:"Copy source",download:"Download",search:"Search",searchPlaceholder:"Search\u2026",searchNext:"Next match",searchPrevious:"Previous match",searchClose:"Close search",searchCount:"{current} / {total}",searchCountCapped:"{current} / {total}+",searchNone:"No matches",searchResults:"{total} matches",wrap:"Toggle line wrap",showMore:"Show all {count} lines",preview:"Preview",source:"Source",split:"Split",swapPanes:"Swap panes",stackPanes:"Stack panes",syncScroll:"Sync scrolling",tabs:"View",actions:"Actions",toc:"Table of contents",anchor:"Link to this section",table:"Table",tree:"Tree",raw:"Raw",expandAll:"Expand all",collapseAll:"Collapse all",copyPath:"Copy path",copyValue:"Copy value",items:"{count} items",item:"1 item",keys:"{count} keys",key:"1 key",showMoreItems:"Show {count} more",showFullString:"Show full string ({count} characters)",truncated:"Partially expanded: too many nodes.",loading:"Loading\u2026",errorTitle:"Unable to display content",invalidJson:"Invalid JSON at line {line}, column {column}: {message}.",invalidJsonRaw:"Invalid JSON at line {line}, column {column} \u2014 showing raw text.",empty:"Nothing to display",tooLarge:"Content is too large ({size} characters, limit {limit}).",jsonInvalid:"This JSON could not be read: {message}",jsonPathMissing:'Nothing was found at "{path}" in this JSON.',jsonUnusable:"This data cannot be shown by this element.",dataNoList:"Expected a list, or an object with a list under {keys}.",tooDeep:"Nesting is too deep (limit {limit}).",tooComplex:"This document is nested too deeply to display.",unserializable:"This value cannot be converted to JSON (circular reference or BigInt).",highlightSkipped:"Content is large: syntax highlighting is disabled.",loadFailed:'Could not load "{url}": {reason}',remoteBlocked:'Cross-origin URL blocked. Add the "allow-remote" attribute to allow it.',unsafeUrl:"URL blocked: only http(s) URLs can be loaded.",timeout:"Request timed out.",added:"Added",removed:"Removed",code:"Code",edit:"Edit",splitView:"Side by side",unifiedView:"Unified",diffStats:"+{added} \u2212{removed}",diffSimplified:"Many changes: the comparison is simplified to removed and added blocks.",noDifferences:"No differences",previousChange:"Previous change",nextChange:"Next change",changePosition:"{current} of {total}",changeTotal:"{count} changes",terminal:"Terminal",command:"Command",copyCommand:"Copy command",copyCommands:"Copy commands",replay:"Replay",showMoreLines:"Show {count} more lines",files:"Files",copyTree:"Copy tree",treeStats:"{folders} folders, {files} files",invalidTree:"This tree could not be read: {message}",treeTruncated:"Only the first {limit} entries are shown.",status_added:"added",status_removed:"removed",status_modified:"modified",status_highlighted:"highlighted",httpExchange:"Exchange",httpRequest:"Request",httpResponse:"Response",httpBody:"Body",httpHeaders:"Headers",httpQuery:"Query",httpNone:"None",httpNoBody:"No body",httpConnection:"Connection",httpEntry:"Entry",httpEntryPrevious:"Previous entry",httpEntryNext:"Next entry",httpEntryCount:"{index} of {total}",httpServerIp:"Server IP",httpVersion:"HTTP version",httpMimeType:"MIME type",httpBodySize:"Body size (on the wire)",httpContentSize:"Content size (decoded)",httpTransferSize:"Transfer size",httpTlsProtocol:"TLS protocol",httpTlsCipher:"Cipher",httpTlsSubject:"Certificate subject",httpTlsSans:"Alternative names",httpTlsIssuer:"Issuer",httpTlsValidFrom:"Valid from",httpTlsValidTo:"Valid to",httpTlsExpired:"expired",httpBinary:"Binary content ({type})",httpImage:"Response image ({type})",copyUrl:"Copy URL",codeLanguage:"Language",showSecrets:"Show secrets",hideSecrets:"Hide secrets",secretsShown:"Secrets shown",secretsHidden:"Secrets hidden",secretsInCode:"Credentials are masked in this code. Replace them with your own.",invalidHttp:"This HTTP message could not be read: {message}",log:"Log",followLog:"Follow new lines",levelToggle:"Show or hide {level} entries",logNoMatch:"No entry matches the filters.",chartView:"Chart",legend:"Legend",seriesToggle:"Show or hide {name}",copyData:"Copy data",chartSummary:"{type} with {series} series and {points} points.",chartRange:"{name} from {min} to {max}",chart_line:"Line chart",chart_area:"Area chart",chart_bar:"Bar chart",chart_pie:"Donut chart",chartError:"This data could not be charted: {message}",chartTruncated:"Only the first 5,000 points of each series are shown.",chartLoadFailed:"The chart library could not be loaded: {message}",openapiInvalid:"This API description could not be read: {message}",openapiYamlFailed:"The YAML reader could not be loaded: {message}",openapiTruncated:"Only the first 2,000 endpoints are shown.",openapiServers:"Servers",openapiAuth:"Authentication",openapiEndpoints:"Endpoints",openapiTags:"Tags",openapiAllTags:"All",openapiNoMatch:"No endpoint matches.",openapiDeprecated:"deprecated",openapiParameters:"Parameters",openapiName:"Name",openapiIn:"In",openapiType:"Type",openapiDescription:"Description",openapiRequired:"required",openapiRequestBody:"Request body",openapiResponses:"Responses",openapiExample:"Example",openapiExampleValue:"Example",unchangedLines:"Show {count} unchanged lines",copyPatch:"Copy patch",changes:"Changes",original:"Original",modified:"Modified",patch:"Patch",tags:"Tags",noTags:"No tags",addTag:"Add a tag",tagPlaceholder:"tag",suggestions:"Suggestions",createTag:'Create "{tag}"',removeTag:"Remove {tag}",tagAdded:"{tag} added",tagRemoved:"{tag} removed",pressAgainToRemove:"Press Backspace again to remove {tag}",tagDuplicate:"{tag} is already selected.",tagDisabled:"{tag} cannot be selected.",tagLimit:"You can select up to {max} tags.",tagNotAllowed:"{tag} is not in the list.",tagTooLong:"{tag} is too long.",tagInvalid:"{tag} is not a valid tag.",tagRefused:"{tag} was refused.",tagsRequired:"Select at least one tag.",tagCount:"{count} tags",tagCountOne:"1 tag",tagCountMax:"{count} / {max} tags",browseTags:"Browse all tags",otherTags:"Other",clearTags:"Remove all tags",filterTags:"Filter tags",tagsFound:"{count} tags",invalidTags:'The tags must be a JSON array, or an object with "value" and "options".',rowsRange:"Rows {from}\u2013{to} of {total}",noRows:"No rows",firstPage:"First page",previousPage:"Previous page",nextPage:"Next page",lastPage:"Last page",sortBy:"Sort by {name}",column:"Column {n}",rowNumber:"Row",csvStatus:"{rows} rows \xD7 {columns} columns",csvUnclosed:"Unclosed quote starting at line {line}.",tooManyColumns:"Only the first {limit} columns are shown.",matchingRows:"{count} matching rows",undo:"Undo",redo:"Redo",fullscreen:"Full screen",exitFullscreen:"Exit full screen",stopEditing:"Stop editing",editor:"Editor",validJson:"Valid JSON"}),fl=Object.freeze({copy:"Copier",copyCode:"Copier le code",copied:"Copi\xE9",copyFailed:"\xC9chec de la copie",copySource:"Copier la source",download:"T\xE9l\xE9charger",search:"Rechercher",searchPlaceholder:"Rechercher\u2026",searchNext:"R\xE9sultat suivant",searchPrevious:"R\xE9sultat pr\xE9c\xE9dent",searchClose:"Fermer la recherche",searchCount:"{current} / {total}",searchCountCapped:"{current} / {total}+",searchNone:"Aucun r\xE9sultat",searchResults:"{total} r\xE9sultats",wrap:"Activer/d\xE9sactiver le retour \xE0 la ligne",showMore:"Afficher les {count} lignes",preview:"Aper\xE7u",source:"Source",split:"C\xF4te \xE0 c\xF4te",swapPanes:"Inverser les panneaux",stackPanes:"Empiler les panneaux",syncScroll:"Synchroniser le d\xE9filement",tabs:"Affichage",actions:"Actions",toc:"Table des mati\xE8res",anchor:"Lien vers cette section",table:"Tableau",tree:"Arbre",raw:"Brut",expandAll:"Tout d\xE9plier",collapseAll:"Tout replier",copyPath:"Copier le chemin",copyValue:"Copier la valeur",items:"{count} \xE9l\xE9ments",item:"1 \xE9l\xE9ment",keys:"{count} cl\xE9s",key:"1 cl\xE9",showMoreItems:"Afficher {count} de plus",showFullString:"Afficher toute la cha\xEEne ({count} caract\xE8res)",truncated:"D\xE9pliage partiel : trop de n\u0153uds.",loading:"Chargement\u2026",errorTitle:"Impossible d\u2019afficher le contenu",invalidJson:"JSON invalide \xE0 la ligne {line}, colonne {column} : {message}.",invalidJsonRaw:"JSON invalide \xE0 la ligne {line}, colonne {column} \u2014 affichage du texte brut.",empty:"Rien \xE0 afficher",tooLarge:"Contenu trop volumineux ({size} caract\xE8res, limite {limit}).",jsonInvalid:"Ce JSON n'a pas pu \xEAtre lu : {message}",jsonPathMissing:"Rien n\u2019a \xE9t\xE9 trouv\xE9 \xE0 \xAB {path} \xBB dans ce JSON.",jsonUnusable:"Ces donn\xE9es ne peuvent pas \xEAtre affich\xE9es par cet \xE9l\xE9ment.",dataNoList:"Une liste \xE9tait attendue, ou un objet avec une liste sous {keys}.",tooDeep:"Imbrication trop profonde (limite {limit}).",tooComplex:"Ce document est trop imbriqu\xE9 pour \xEAtre affich\xE9.",unserializable:"Cette valeur ne peut pas \xEAtre convertie en JSON (r\xE9f\xE9rence circulaire ou BigInt).",highlightSkipped:"Contenu volumineux : coloration syntaxique d\xE9sactiv\xE9e.",loadFailed:"Impossible de charger \xAB {url} \xBB : {reason}",remoteBlocked:"URL d\u2019une autre origine bloqu\xE9e. Ajoutez l\u2019attribut \xAB allow-remote \xBB pour l\u2019autoriser.",unsafeUrl:"URL bloqu\xE9e : seules les URL http(s) peuvent \xEAtre charg\xE9es.",timeout:"D\xE9lai de la requ\xEAte d\xE9pass\xE9.",added:"Ajout\xE9",removed:"Supprim\xE9",code:"Code",edit:"Modifier",splitView:"C\xF4te \xE0 c\xF4te",unifiedView:"Unifi\xE9",diffStats:"+{added} \u2212{removed}",diffSimplified:"Beaucoup de changements : la comparaison est simplifi\xE9e en blocs retir\xE9s et ajout\xE9s.",noDifferences:"Aucune diff\xE9rence",previousChange:"Modification pr\xE9c\xE9dente",nextChange:"Modification suivante",changePosition:"{current} sur {total}",changeTotal:"Modifications : {count}",terminal:"Terminal",command:"Commande",copyCommand:"Copier la commande",copyCommands:"Copier les commandes",replay:"Rejouer",showMoreLines:"Afficher {count} lignes de plus",files:"Fichiers",copyTree:"Copier l'arborescence",treeStats:"{folders} dossiers, {files} fichiers",invalidTree:"Impossible de lire cette arborescence : {message}",treeTruncated:"Seules les {limit} premi\xE8res entr\xE9es sont affich\xE9es.",status_added:"ajout\xE9",status_removed:"supprim\xE9",status_modified:"modifi\xE9",status_highlighted:"mis en \xE9vidence",httpExchange:"\xC9change",httpRequest:"Requ\xEAte",httpResponse:"R\xE9ponse",httpBody:"Corps",httpHeaders:"En-t\xEAtes",httpQuery:"Param\xE8tres",httpNone:"Aucun",httpNoBody:"Pas de corps",httpConnection:"Connexion",httpEntry:"Entr\xE9e",httpEntryPrevious:"Entr\xE9e pr\xE9c\xE9dente",httpEntryNext:"Entr\xE9e suivante",httpEntryCount:"{index} sur {total}",httpServerIp:"IP du serveur",httpVersion:"Version HTTP",httpMimeType:"Type MIME",httpBodySize:"Taille du corps (transmise)",httpContentSize:"Taille du contenu (d\xE9cod\xE9)",httpTransferSize:"Taille transf\xE9r\xE9e",httpTlsProtocol:"Protocole TLS",httpTlsCipher:"Chiffrement",httpTlsSubject:"Sujet du certificat",httpTlsSans:"Noms alternatifs",httpTlsIssuer:"\xC9metteur",httpTlsValidFrom:"Valide \xE0 partir du",httpTlsValidTo:"Valide jusqu\u2019au",httpTlsExpired:"expir\xE9",httpBinary:"Contenu binaire ({type})",httpImage:"Image de la r\xE9ponse ({type})",copyUrl:"Copier l'URL",codeLanguage:"Langage",showSecrets:"Afficher les secrets",hideSecrets:"Masquer les secrets",secretsShown:"Secrets affich\xE9s",secretsHidden:"Secrets masqu\xE9s",secretsInCode:"Les identifiants sont masqu\xE9s dans ce code. Remplacez-les par les v\xF4tres.",invalidHttp:"Impossible de lire ce message HTTP : {message}",log:"Journal",followLog:"Suivre les nouvelles lignes",levelToggle:"Afficher ou masquer les entr\xE9es {level}",logNoMatch:"Aucune entr\xE9e ne correspond aux filtres.",chartView:"Graphique",legend:"L\xE9gende",seriesToggle:"Afficher ou masquer {name}",copyData:"Copier les donn\xE9es",chartSummary:"{type} avec {series} s\xE9ries et {points} points.",chartRange:"{name} de {min} \xE0 {max}",chart_line:"Graphique en courbes",chart_area:"Graphique en aires",chart_bar:"Graphique en barres",chart_pie:"Graphique en anneau",chartError:"Impossible de tracer ces donn\xE9es : {message}",chartTruncated:"Seuls les 5 000 premiers points de chaque s\xE9rie sont affich\xE9s.",chartLoadFailed:"Impossible de charger la biblioth\xE8que de graphiques : {message}",openapiInvalid:"Impossible de lire cette description d\u2019API : {message}",openapiYamlFailed:"Impossible de charger le lecteur YAML : {message}",openapiTruncated:"Seuls les 2 000 premiers points d\u2019acc\xE8s sont affich\xE9s.",openapiServers:"Serveurs",openapiAuth:"Authentification",openapiEndpoints:"Points d\u2019acc\xE8s",openapiTags:"Tags",openapiAllTags:"Tous",openapiNoMatch:"Aucun point d\u2019acc\xE8s ne correspond.",openapiDeprecated:"obsol\xE8te",openapiParameters:"Param\xE8tres",openapiName:"Nom",openapiIn:"Emplacement",openapiType:"Type",openapiDescription:"Description",openapiRequired:"requis",openapiRequestBody:"Corps de la requ\xEAte",openapiResponses:"R\xE9ponses",openapiExample:"Exemple",openapiExampleValue:"Exemple",unchangedLines:"Afficher {count} lignes inchang\xE9es",copyPatch:"Copier le patch",changes:"Modifications",original:"Original",modified:"Modifi\xE9",patch:"Patch",tags:"Tags",noTags:"Aucun tag",addTag:"Ajouter un tag",tagPlaceholder:"tag",suggestions:"Suggestions",createTag:"Cr\xE9er \xAB {tag} \xBB",removeTag:"Retirer {tag}",tagAdded:"{tag} ajout\xE9",tagRemoved:"{tag} retir\xE9",pressAgainToRemove:"Appuyez de nouveau sur Retour arri\xE8re pour retirer {tag}",tagDuplicate:"{tag} est d\xE9j\xE0 s\xE9lectionn\xE9.",tagDisabled:"{tag} ne peut pas \xEAtre s\xE9lectionn\xE9.",tagLimit:"Vous pouvez s\xE9lectionner jusqu\u2019\xE0 {max} tags.",tagNotAllowed:"{tag} n\u2019est pas dans la liste.",tagTooLong:"{tag} est trop long.",tagInvalid:"{tag} n\u2019est pas un tag valide.",tagRefused:"{tag} a \xE9t\xE9 refus\xE9.",tagsRequired:"S\xE9lectionnez au moins un tag.",tagCount:"{count} tags",tagCountOne:"1 tag",tagCountMax:"{count} / {max} tags",browseTags:"Parcourir tous les tags",otherTags:"Autres",clearTags:"Retirer tous les tags",filterTags:"Filtrer les tags",tagsFound:"{count} tags",invalidTags:"Les tags doivent \xEAtre un tableau JSON, ou un objet avec \xAB value \xBB et \xAB options \xBB.",rowsRange:"Lignes {from}\u2013{to} sur {total}",noRows:"Aucune ligne",firstPage:"Premi\xE8re page",previousPage:"Page pr\xE9c\xE9dente",nextPage:"Page suivante",lastPage:"Derni\xE8re page",sortBy:"Trier par {name}",column:"Colonne {n}",rowNumber:"Ligne",csvStatus:"{rows} lignes \xD7 {columns} colonnes",csvUnclosed:"Guillemet non ferm\xE9 \xE0 partir de la ligne {line}.",tooManyColumns:"Seules les {limit} premi\xE8res colonnes sont affich\xE9es.",matchingRows:"{count} lignes correspondantes",undo:"Annuler",redo:"R\xE9tablir",fullscreen:"Plein \xE9cran",exitFullscreen:"Quitter le plein \xE9cran",stopEditing:"Terminer la modification",editor:"\xC9diteur",validJson:"JSON valide"}),rs={},wn=new Map;function En(n){for(let[e,t]of Object.entries(n))e==="en"?Object.assign(rs,t):wn.set(e,{...wn.get(e)??{},...t});for(let e of _r)e()}var ts=new Map([["en",ns],["fr",fl]]);var _r=new Set;function as(n){return _r.add(n),()=>_r.delete(n)}function wr(n){let e=ts.get(n),t=ts.get(String(n).split("-")[0]);return(r,a)=>{let s=String(n).split("-")[0],i=e?.[r]??t?.[r]??wn.get(n)?.[r]??wn.get(s)?.[r]??ns[r]??rs[r]??String(r);return a?i.replace(/\{(\w+)\}/g,(o,c)=>Object.prototype.hasOwnProperty.call(a,c)?String(a[c]):o):i}}function dt(n,e){try{return new Intl.NumberFormat(e).format(n)}catch{return String(n)}}var ss=`/* Vitrine Light \u2014 default light theme. Values: docs/DESIGN_SYSTEM.md \xA72. */
[data-theme='light'] {
  color-scheme: light;
  --vt-bg: #f3f4f1;
  --vt-surface: #ffffff;
  --vt-surface-sunken: #eaece7;
  --vt-surface-raised: #ffffff;
  --vt-border: #d6d9d2;
  --vt-border-strong: #b9beb4;
  --vt-fg: #11151c;
  --vt-fg-muted: #4a5260;
  --vt-accent: #14b8a6;
  --vt-accent-fg: #0a6e6f;
  --vt-on-accent: #11151c;
  --vt-accent-soft: rgba(20, 184, 166, 0.12);
  --vt-highlight: rgba(242, 169, 59, 0.35);
  --vt-highlight-current: rgba(242, 169, 59, 0.7);
  --vt-line-highlight: rgba(20, 184, 166, 0.1);
  --vt-success: #0a6e6f;
  --vt-warning: #a6510b;
  --vt-danger: #b2384f;
  --vt-info: #2f55c9;
  --vt-diff-added: rgba(20, 184, 166, 0.12);
  --vt-diff-removed: rgba(178, 56, 79, 0.12);
  --vt-shadow: 0 8px 24px rgba(17, 21, 28, 0.12);
  --vt-syntax-keyword: #7a3ec8;
  --vt-syntax-string: #0a6e6f;
  --vt-syntax-number: #a6510b;
  --vt-syntax-function: #2f55c9;
  --vt-syntax-type: #b2384f;
  --vt-syntax-comment: #5f6773;
  --vt-syntax-attr: #2f55c9;
  --vt-syntax-tag: #b2384f;
  --vt-syntax-meta: #4a5260;
}
`;var is=`/* Vitrine Dark \u2014 default dark theme. Values: docs/DESIGN_SYSTEM.md \xA72. */
[data-theme='dark'] {
  color-scheme: dark;
  --vt-bg: #11151c;
  --vt-surface: #171c25;
  --vt-surface-sunken: #0c0f14;
  --vt-surface-raised: #1e2430;
  --vt-border: #262d3a;
  --vt-border-strong: #3a4354;
  --vt-fg: #e8eae6;
  --vt-fg-muted: #9aa3b2;
  --vt-accent: #14b8a6;
  --vt-accent-fg: #14b8a6;
  --vt-on-accent: #11151c;
  --vt-accent-soft: rgba(20, 184, 166, 0.16);
  --vt-highlight: rgba(242, 169, 59, 0.3);
  --vt-highlight-current: rgba(242, 169, 59, 0.6);
  --vt-line-highlight: rgba(20, 184, 166, 0.12);
  --vt-success: #14b8a6;
  --vt-warning: #f2a93b;
  --vt-danger: #ff8f73;
  --vt-info: #7c9cff;
  --vt-diff-added: rgba(20, 184, 166, 0.16);
  --vt-diff-removed: rgba(255, 143, 115, 0.14);
  --vt-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  --vt-syntax-keyword: #c4a5ff;
  --vt-syntax-string: #5eead4;
  --vt-syntax-number: #f2a93b;
  --vt-syntax-function: #7c9cff;
  --vt-syntax-type: #ff8f73;
  --vt-syntax-comment: #8a93a3;
  --vt-syntax-attr: #7c9cff;
  --vt-syntax-tag: #ff8f73;
  --vt-syntax-meta: #9aa3b2;
}
`;var os=`/* Vitrine Dim \u2014 softer, blue-grey dark theme for long reading sessions. */
[data-theme='dim'] {
  color-scheme: dark;
  --vt-bg: #1b2230;
  --vt-surface: #212a3a;
  --vt-surface-sunken: #192030;
  --vt-surface-raised: #29334a;
  --vt-border: #33405a;
  --vt-border-strong: #46557a;
  --vt-fg: #dce2ec;
  --vt-fg-muted: #a3adc0;
  --vt-accent: #14b8a6;
  --vt-accent-fg: #2dd4bf;
  --vt-on-accent: #11151c;
  --vt-accent-soft: rgba(45, 212, 191, 0.16);
  --vt-highlight: rgba(242, 169, 59, 0.3);
  --vt-highlight-current: rgba(242, 169, 59, 0.6);
  --vt-line-highlight: rgba(45, 212, 191, 0.12);
  --vt-success: #2dd4bf;
  --vt-warning: #f2a93b;
  --vt-danger: #ff9b82;
  --vt-info: #8faeff;
  --vt-diff-added: rgba(45, 212, 191, 0.16);
  --vt-diff-removed: rgba(255, 155, 130, 0.16);
  --vt-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  --vt-syntax-keyword: #c9aeff;
  --vt-syntax-string: #6ee7d5;
  --vt-syntax-number: #f5b85c;
  --vt-syntax-function: #8faeff;
  --vt-syntax-type: #ff9b82;
  --vt-syntax-comment: #95a0b5;
  --vt-syntax-attr: #8faeff;
  --vt-syntax-tag: #ff9b82;
  --vt-syntax-meta: #a3adc0;
}
`;var ls=`/* Vitrine Paper \u2014 warm, low-glare light theme. */
[data-theme='paper'] {
  color-scheme: light;
  --vt-bg: #f4efe4;
  --vt-surface: #fbf8f1;
  --vt-surface-sunken: #f0e9da;
  --vt-surface-raised: #fffdf8;
  --vt-border: #ddd3c0;
  --vt-border-strong: #c3b79f;
  --vt-fg: #2b2620;
  --vt-fg-muted: #5c5347;
  --vt-accent: #14b8a6;
  --vt-accent-fg: #0a6566;
  --vt-on-accent: #11151c;
  --vt-accent-soft: rgba(20, 184, 166, 0.14);
  --vt-highlight: rgba(242, 169, 59, 0.38);
  --vt-highlight-current: rgba(242, 169, 59, 0.72);
  --vt-line-highlight: rgba(20, 184, 166, 0.11);
  --vt-success: #0a6566;
  --vt-warning: #974a09;
  --vt-danger: #a63148;
  --vt-info: #2b4fbd;
  --vt-diff-added: rgba(20, 184, 166, 0.14);
  --vt-diff-removed: rgba(166, 49, 72, 0.12);
  --vt-shadow: 0 8px 24px rgba(43, 38, 32, 0.12);
  --vt-syntax-keyword: #7239bd;
  --vt-syntax-string: #0a6566;
  --vt-syntax-number: #974a09;
  --vt-syntax-function: #2b4fbd;
  --vt-syntax-type: #a63148;
  --vt-syntax-comment: #6b6255;
  --vt-syntax-attr: #2b4fbd;
  --vt-syntax-tag: #a63148;
  --vt-syntax-meta: #5c5347;
}
`;var cs=`/* Vitrine High Contrast \u2014 maximum legibility (WCAG AAA text contrast). */
[data-theme='high-contrast'] {
  color-scheme: dark;
  --vt-bg: #000000;
  --vt-surface: #000000;
  --vt-surface-sunken: #0a0a0a;
  --vt-surface-raised: #141414;
  --vt-border: #8a8a8a;
  --vt-border-strong: #ffffff;
  --vt-fg: #ffffff;
  --vt-fg-muted: #d6d6d6;
  --vt-accent: #2ee6d0;
  --vt-accent-fg: #5eead4;
  --vt-on-accent: #000000;
  --vt-accent-soft: rgba(46, 230, 208, 0.22);
  --vt-highlight: rgba(255, 214, 0, 0.35);
  --vt-highlight-current: rgba(255, 214, 0, 0.55);
  --vt-line-highlight: rgba(46, 230, 208, 0.18);
  --vt-success: #5eead4;
  --vt-warning: #ffd166;
  --vt-danger: #ffa08a;
  --vt-info: #a8c1ff;
  --vt-diff-added: rgba(46, 230, 208, 0.22);
  --vt-diff-removed: rgba(255, 160, 138, 0.24);
  --vt-shadow: 0 0 0 1px #ffffff;
  --vt-syntax-keyword: #dcc2ff;
  --vt-syntax-string: #7cf5e0;
  --vt-syntax-number: #ffd166;
  --vt-syntax-function: #a8c1ff;
  --vt-syntax-type: #ffb3a1;
  --vt-syntax-comment: #c8c8c8;
  --vt-syntax-attr: #a8c1ff;
  --vt-syntax-tag: #ffb3a1;
  --vt-syntax-meta: #e0e0e0;
}
`;var Nd=Object.freeze(["bg","surface","surface-sunken","surface-raised","border","border-strong","fg","fg-muted","accent","accent-fg","on-accent","accent-soft","highlight","highlight-current","line-highlight","success","warning","danger","info","diff-added","diff-removed","shadow","syntax-keyword","syntax-string","syntax-number","syntax-function","syntax-type","syntax-comment","syntax-attr","syntax-tag","syntax-meta"]),pt=new Map,ht=new CSSStyleSheet;function xl(n){let e=/\[data-theme='([a-z0-9-]+)'\]/.exec(n)?.[1];if(!e)throw new Error("[vitrine] Theme file without a [data-theme] selector.");let t=/color-scheme:\s*(light|dark)\s*;/.exec(n)?.[1]==="dark"?"dark":"light",r={};for(let[,a,s]of n.matchAll(/--vt-([a-z0-9-]+)\s*:\s*([^;]+);/g))r[a]=s.trim();return{name:e,definition:{colorScheme:t,tokens:r}}}for(let n of[ss,is,os,ls,cs]){let{name:e,definition:t}=xl(n);pt.set(e,t)}var Cd=Object.freeze([...pt.keys()]);function us(n){let e=pt.get(n);return e?{colorScheme:e.colorScheme,tokens:{...e.tokens}}:void 0}function _l(){for(;ht.cssRules.length;)ht.deleteRule(0);for(let[n,e]of pt){let t=ht.insertRule(`.vt[data-theme="${n}"] {}`,ht.cssRules.length),r=ht.cssRules[t].style;r.setProperty("color-scheme",e.colorScheme);for(let[a,s]of Object.entries(e.tokens))r.setProperty(`--_${a}`,`var(--vt-${a}, ${s})`)}}_l();var Er=typeof matchMedia=="function"?matchMedia("(prefers-color-scheme: dark)"):null,Ar=new Set;function wl(){for(let n of Ar)n()}Er?.addEventListener?.("change",wl);function ds(n){return Ar.add(n),()=>Ar.delete(n)}function hs(n){let e=W(),t=n?.trim().toLowerCase()||e.theme;if(t!=="auto"&&!pt.has(t)&&(t=pt.has(e.theme)?e.theme:"auto"),t!=="auto")return t;let r=Er?.matches?e.darkTheme:e.lightTheme;return pt.has(r)?r:Er?.matches?"dark":"light"}var El="",Al="",Sl="";function ps(){return El}function An(){return Sl}function fs(){return Al}var ms=Object.freeze({"1c-light":0,"a11y-dark":1,"a11y-light":0,agate:1,"an-old-hope":1,androidstudio:1,"arduino-light":0,arta:1,ascetic:0,"atom-one-dark":1,"atom-one-dark-reasonable":1,"atom-one-light":0,"base16-3024":1,"base16-apathy":1,"base16-apprentice":1,"base16-ashes":1,"base16-atelier-cave":1,"base16-atelier-cave-light":0,"base16-atelier-dune":1,"base16-atelier-dune-light":0,"base16-atelier-estuary":1,"base16-atelier-estuary-light":0,"base16-atelier-forest":1,"base16-atelier-forest-light":0,"base16-atelier-heath":1,"base16-atelier-heath-light":0,"base16-atelier-lakeside":1,"base16-atelier-lakeside-light":0,"base16-atelier-plateau":1,"base16-atelier-plateau-light":0,"base16-atelier-savanna":1,"base16-atelier-savanna-light":0,"base16-atelier-seaside":1,"base16-atelier-seaside-light":0,"base16-atelier-sulphurpool":1,"base16-atelier-sulphurpool-light":0,"base16-atlas":1,"base16-bespin":1,"base16-black-metal":1,"base16-black-metal-bathory":1,"base16-black-metal-burzum":1,"base16-black-metal-dark-funeral":1,"base16-black-metal-gorgoroth":1,"base16-black-metal-immortal":1,"base16-black-metal-khold":1,"base16-black-metal-marduk":1,"base16-black-metal-mayhem":1,"base16-black-metal-nile":1,"base16-black-metal-venom":1,"base16-brewer":1,"base16-bright":1,"base16-brogrammer":1,"base16-brush-trees":0,"base16-brush-trees-dark":1,"base16-chalk":1,"base16-circus":1,"base16-classic-dark":1,"base16-classic-light":0,"base16-codeschool":1,"base16-colors":1,"base16-cupcake":0,"base16-cupertino":0,"base16-danqing":1,"base16-darcula":1,"base16-dark-violet":1,"base16-darkmoss":1,"base16-darktooth":1,"base16-decaf":1,"base16-default-dark":1,"base16-default-light":0,"base16-dirtysea":0,"base16-dracula":1,"base16-edge-dark":1,"base16-edge-light":0,"base16-eighties":1,"base16-embers":1,"base16-equilibrium-dark":1,"base16-equilibrium-gray-dark":1,"base16-equilibrium-gray-light":0,"base16-equilibrium-light":0,"base16-espresso":1,"base16-eva":1,"base16-eva-dim":1,"base16-flat":1,"base16-framer":1,"base16-fruit-soda":0,"base16-gigavolt":1,"base16-github":0,"base16-google-dark":1,"base16-google-light":0,"base16-grayscale-dark":1,"base16-grayscale-light":0,"base16-green-screen":1,"base16-gruvbox-dark-hard":1,"base16-gruvbox-dark-medium":1,"base16-gruvbox-dark-pale":1,"base16-gruvbox-dark-soft":1,"base16-gruvbox-light-hard":0,"base16-gruvbox-light-medium":0,"base16-gruvbox-light-soft":0,"base16-hardcore":1,"base16-harmonic16-dark":1,"base16-harmonic16-light":0,"base16-heetch-dark":1,"base16-heetch-light":0,"base16-helios":1,"base16-hopscotch":1,"base16-horizon-dark":1,"base16-horizon-light":0,"base16-humanoid-dark":1,"base16-humanoid-light":0,"base16-ia-dark":1,"base16-ia-light":0,"base16-icy-dark":1,"base16-ir-black":1,"base16-isotope":1,"base16-kimber":1,"base16-london-tube":1,"base16-macintosh":1,"base16-marrakesh":1,"base16-materia":1,"base16-material":1,"base16-material-darker":1,"base16-material-lighter":0,"base16-material-palenight":1,"base16-material-vivid":1,"base16-mellow-purple":1,"base16-mexico-light":0,"base16-mocha":1,"base16-monokai":1,"base16-nebula":1,"base16-nord":1,"base16-nova":1,"base16-ocean":1,"base16-oceanicnext":1,"base16-one-light":0,"base16-onedark":1,"base16-outrun-dark":1,"base16-papercolor-dark":1,"base16-papercolor-light":0,"base16-paraiso":1,"base16-pasque":1,"base16-phd":1,"base16-pico":1,"base16-pop":1,"base16-porple":1,"base16-qualia":1,"base16-railscasts":1,"base16-rebecca":1,"base16-ros-pine":1,"base16-ros-pine-dawn":0,"base16-ros-pine-moon":1,"base16-sagelight":0,"base16-sandcastle":1,"base16-seti-ui":1,"base16-shapeshifter":0,"base16-silk-dark":1,"base16-silk-light":0,"base16-snazzy":1,"base16-solar-flare":1,"base16-solar-flare-light":0,"base16-solarized-dark":1,"base16-solarized-light":0,"base16-spacemacs":1,"base16-summercamp":1,"base16-summerfruit-dark":1,"base16-summerfruit-light":0,"base16-synth-midnight-terminal-dark":1,"base16-synth-midnight-terminal-light":0,"base16-tango":1,"base16-tender":1,"base16-tomorrow":0,"base16-tomorrow-night":1,"base16-twilight":1,"base16-unikitty-dark":1,"base16-unikitty-light":0,"base16-vulcan":1,"base16-windows-10":1,"base16-windows-10-light":0,"base16-windows-95":1,"base16-windows-95-light":0,"base16-windows-high-contrast":1,"base16-windows-high-contrast-light":0,"base16-windows-nt":1,"base16-windows-nt-light":0,"base16-woodland":1,"base16-xcode-dusk":1,"base16-zenburn":1,"brown-paper":0,"codepen-embed":1,"color-brewer":0,"cybertopia-cherry":0,"cybertopia-dimmer":0,"cybertopia-icecap":0,"cybertopia-saturated":0,dark:1,default:0,devibeans:1,docco:0,equinox:0,far:1,felipec:1,foundation:0,github:0,"github-dark":1,"github-dark-dimmed":1,gml:1,googlecode:0,"gradient-dark":1,"gradient-light":0,grayscale:0,hybrid:1,idea:0,"intellij-light":0,"ir-black":1,"isbl-editor-dark":1,"isbl-editor-light":0,"kimbie-dark":1,"kimbie-light":0,lightfair:0,lioshi:1,magula:0,"mono-blue":0,monokai:1,"monokai-sublime":1,"night-owl":1,"nnfx-dark":1,"nnfx-light":0,nord:1,obsidian:1,"panda-syntax-dark":1,"panda-syntax-light":0,"paraiso-dark":1,"paraiso-light":0,pojoaque:0,purebasic:0,"qtcreator-dark":1,"qtcreator-light":0,rainbow:1,"rose-pine":1,"rose-pine-dawn":0,"rose-pine-moon":1,routeros:0,"school-book":0,"shades-of-purple":1,srcery:1,"stackoverflow-dark":1,"stackoverflow-light":0,sunburst:1,"tokyo-night-dark":1,"tokyo-night-light":0,"tomorrow-night-blue":1,"tomorrow-night-bright":1,vs:0,"vs-dark":1,vs2015:1,xcode:0,xt256:1});var Sr=new Map,gs=new Map;function bs(n){if(typeof n!="string")return null;let e=n.trim().toLowerCase().replace(/\//g,"-");return!e||e.length>60?null:Object.prototype.hasOwnProperty.call(ms,e)?e:null}function ys(n){return gs.get(n)}function vs(n){let e=Sr.get(n);if(e)return e;let t=Tl(n);return Sr.set(n,t),t}async function Tl(n){let e=W().syntaxThemesUrl||fs();if(!e)return null;try{let t=new URL(`${n}.css`,new URL(e.endsWith("/")?e:`${e}/`,document.baseURI));if(t.protocol!=="https:"&&t.protocol!=="http:")return null;let r=await fetch(t.href,{credentials:"same-origin"});if(!r.ok)throw new Error(`HTTP ${r.status}`);let a=await r.text(),s=new CSSStyleSheet;return s.replaceSync(a),gs.set(n,s),s}catch(t){return console.warn(`[vitrine] Could not load the "${n}" syntax theme.`,t),Sr.delete(n),null}}var xs="http://www.w3.org/2000/svg";var Yt=["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"}],Zt=["path",{d:"M14 2v4a2 2 0 0 0 2 2h4"}],kl={copy:[["rect",{width:"14",height:"14",x:"8",y:"8",rx:"2",ry:"2"}],["path",{d:"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"}]],check:[["path",{d:"M20 6 9 17l-5-5"}]],search:[["path",{d:"m21 21-4.34-4.34"}],["circle",{cx:"11",cy:"11",r:"8"}]],"chevron-up":[["path",{d:"m18 15-6-6-6 6"}]],"chevron-down":[["path",{d:"m6 9 6 6 6-6"}]],"chevron-right":[["path",{d:"m9 18 6-6-6-6"}]],wrap:[["path",{d:"m16 16-3 3 3 3"}],["path",{d:"M3 12h14.5a1 1 0 0 1 0 7H13"}],["path",{d:"M3 19h6"}],["path",{d:"M3 5h18"}]],download:[["path",{d:"M12 15V3"}],["path",{d:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"}],["path",{d:"m7 10 5 5 5-5"}]],"expand-all":[["path",{d:"m7 15 5 5 5-5"}],["path",{d:"m7 9 5-5 5 5"}]],"collapse-all":[["path",{d:"m7 20 5-5 5 5"}],["path",{d:"m7 4 5 5 5-5"}]],link:[["path",{d:"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"}],["path",{d:"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"}]],eye:[["path",{d:"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"}],["circle",{cx:"12",cy:"12",r:"3"}]],code:[["path",{d:"m16 18 6-6-6-6"}],["path",{d:"m8 6-6 6 6 6"}]],columns:[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M12 3v18"}]],list:[["path",{d:"M3 5h.01"}],["path",{d:"M3 12h.01"}],["path",{d:"M3 19h.01"}],["path",{d:"M8 5h13"}],["path",{d:"M8 12h13"}],["path",{d:"M8 19h13"}]],pencil:[["path",{d:"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"}],["path",{d:"m15 5 4 4"}]],"chevron-left":[["path",{d:"m15 18-6-6 6-6"}]],"chevrons-left":[["path",{d:"m11 17-5-5 5-5"}],["path",{d:"m18 17-5-5 5-5"}]],"chevrons-right":[["path",{d:"m6 17 5-5-5-5"}],["path",{d:"m13 17 5-5-5-5"}]],sort:[["path",{d:"m21 16-4 4-4-4"}],["path",{d:"M17 20V4"}],["path",{d:"m3 8 4-4 4 4"}],["path",{d:"M7 4v16"}]],"sort-up":[["path",{d:"m5 12 7-7 7 7"}],["path",{d:"M12 19V5"}]],"sort-down":[["path",{d:"M12 5v14"}],["path",{d:"m19 12-7 7-7-7"}]],table:[["path",{d:"M12 3v18"}],["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M3 9h18"}],["path",{d:"M3 15h18"}]],undo:[["path",{d:"M9 14 4 9l5-5"}],["path",{d:"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"}]],redo:[["path",{d:"m15 14 5-5-5-5"}],["path",{d:"M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"}]],maximize:[["path",{d:"M15 3h6v6"}],["path",{d:"m21 3-7 7"}],["path",{d:"m3 21 7-7"}],["path",{d:"M9 21H3v-6"}]],minimize:[["path",{d:"m14 10 7-7"}],["path",{d:"M20 10h-6V4"}],["path",{d:"m3 21 7-7"}],["path",{d:"M4 14h6v6"}]],swap:[["path",{d:"M8 3 4 7l4 4"}],["path",{d:"M4 7h16"}],["path",{d:"m16 21 4-4-4-4"}],["path",{d:"M20 17H4"}]],filter:[["path",{d:"M22 3H2l8 9.46V19l4 2v-8.54L22 3z"}]],keyboard:[["rect",{width:"20",height:"16",x:"2",y:"4",rx:"2"}],["path",{d:"M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"}]],rows:[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M3 12h18"}]],"sync-scroll":[["path",{d:"M9 17H7A5 5 0 0 1 7 7h2"}],["path",{d:"M15 7h2a5 5 0 1 1 0 10h-2"}],["line",{x1:"8",x2:"16",y1:"12",y2:"12"}]],alert:[["path",{d:"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"}],["path",{d:"M12 9v4"}],["path",{d:"M12 17h.01"}]],close:[["path",{d:"M18 6 6 18"}],["path",{d:"m6 6 12 12"}]],replay:[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"}],["path",{d:"M3 3v5h5"}]],chart:[["path",{d:"M3 3v16a2 2 0 0 0 2 2h16"}],["path",{d:"m19 9-5 5-4-4-3 3"}]],follow:[["path",{d:"M12 17V3"}],["path",{d:"m6 11 6 6 6-6"}],["path",{d:"M19 21H5"}]],terminal:[["path",{d:"M12 19h8"}],["path",{d:"m4 17 6-6-6-6"}]],folder:[["path",{d:"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"}]],"folder-open":[["path",{d:"m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"}]],file:[Yt,Zt],"file-code":[Yt,Zt,["path",{d:"m10 13-2 2 2 2"}],["path",{d:"m14 17 2-2-2-2"}]],"file-text":[Yt,Zt,["path",{d:"M10 9H8"}],["path",{d:"M16 13H8"}],["path",{d:"M16 17H8"}]],"file-image":[Yt,Zt,["circle",{cx:"10",cy:"12",r:"2"}],["path",{d:"m20 17-1.296-1.296a2.41 2.41 0 0 0-3.408 0L9 22"}]],"file-data":[Yt,Zt,["path",{d:"M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"}],["path",{d:"M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1"}]],lock:[["rect",{width:"18",height:"11",x:"3",y:"11",rx:"2",ry:"2"}],["path",{d:"M7 11V7a5 5 0 0 1 10 0v4"}]],"eye-off":[["path",{d:"M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"}],["path",{d:"M14.084 14.158a3 3 0 0 1-4.242-4.242"}],["path",{d:"M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"}],["path",{d:"m2 2 20 20"}]],"status-circle":[["circle",{cx:"12",cy:"12",r:"9"}]],"status-running":[["path",{d:"M21 12a9 9 0 1 1-6.22-8.56"}]],"status-skipped":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m5.7 5.7 12.6 12.6"}]],"status-success":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m8.5 12 2.5 2.5 4.5-5"}]],"status-failure":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m15 9-6 6"}],["path",{d:"m9 9 6 6"}]],plus:[["path",{d:"M5 12h14"}],["path",{d:"M12 5v14"}]],trash:[["path",{d:"M3 6h18"}],["path",{d:"M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"}],["path",{d:"M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"}]],"dots-vertical":[["circle",{cx:"12",cy:"12",r:"1"}],["circle",{cx:"12",cy:"5",r:"1"}],["circle",{cx:"12",cy:"19",r:"1"}]],upload:[["path",{d:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"}],["path",{d:"m17 8-5-5-5 5"}],["path",{d:"M12 3v12"}]],help:[["circle",{cx:"12",cy:"12",r:"10"}],["path",{d:"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"}],["path",{d:"M12 17h.01"}]],grip:[["circle",{cx:"9",cy:"5",r:"1"}],["circle",{cx:"9",cy:"12",r:"1"}],["circle",{cx:"9",cy:"19",r:"1"}],["circle",{cx:"15",cy:"5",r:"1"}],["circle",{cx:"15",cy:"12",r:"1"}],["circle",{cx:"15",cy:"19",r:"1"}]],calendar:[["rect",{width:"18",height:"18",x:"3",y:"4",rx:"2"}],["path",{d:"M16 2v4"}],["path",{d:"M8 2v4"}],["path",{d:"M3 10h18"}]],user:[["circle",{cx:"12",cy:"8",r:"5"}],["path",{d:"M20 21a8 8 0 0 0-16 0"}]],history:[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"}],["path",{d:"M3 3v5h5"}],["path",{d:"M12 7v5l4 2"}]],"arrow-right":[["path",{d:"M5 12h14"}],["path",{d:"m12 5 7 7-7 7"}]],minus:[["path",{d:"M5 12h14"}]],refresh:[["path",{d:"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"}],["path",{d:"M21 3v5h-5"}],["path",{d:"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"}],["path",{d:"M8 16H3v5"}]],key:[["path",{d:"M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"}],["circle",{cx:"16.5",cy:"7.5",r:".5"}]],"shield-check":[["path",{d:"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{d:"m9 12 2 2 4-4"}]],"shield-alert":[["path",{d:"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{d:"M12 8v4"}],["path",{d:"M12 16h.01"}]],"arrow-up":[["path",{d:"m5 12 7-7 7 7"}],["path",{d:"M12 19V5"}]],star:[["path",{d:"M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"}]],fork:[["circle",{cx:"12",cy:"18",r:"3"}],["circle",{cx:"6",cy:"6",r:"3"}],["circle",{cx:"18",cy:"6",r:"3"}],["path",{d:"M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9"}],["path",{d:"M12 12v3"}]],issue:[["circle",{cx:"12",cy:"12",r:"10"}],["circle",{cx:"12",cy:"12",r:"1"}]],tag:[["path",{d:"M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"}],["circle",{cx:"7.5",cy:"7.5",r:".5"}]],scale:[["path",{d:"m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"}],["path",{d:"m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"}],["path",{d:"M7 21h10"}],["path",{d:"M12 3v18"}],["path",{d:"M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"}]]};function Pe(n){let e=document.createElementNS(xs,"svg");e.setAttribute("viewBox","0 0 24 24"),e.setAttribute("fill","none"),e.setAttribute("stroke","currentColor"),e.setAttribute("stroke-width","2.1"),e.setAttribute("stroke-linecap","round"),e.setAttribute("stroke-linejoin","round"),e.setAttribute("aria-hidden","true"),e.setAttribute("focusable","false"),e.setAttribute("class","icon");for(let[t,r]of kl[n]??[]){let a=document.createElementNS(xs,t);for(let[s,i]of Object.entries(r))a.setAttribute(s,i);e.append(a)}return e}var Tr=new WeakMap,Jt=null;function Nl(){return Jt||typeof IntersectionObserver>"u"||(Jt=new IntersectionObserver(n=>{for(let e of n)e.isIntersecting&&kr(e.target)},{rootMargin:"600px 0px"})),Jt}function _s(n,e){Tr.set(n,e);let t=Nl();t?t.observe(n):kr(n)}function kr(n){let e=Tr.get(n);e&&(Tr.delete(n),Jt?.unobserve(n),e())}function ws(n){for(let e of Array.from(n.querySelectorAll(".chunk[data-pending]")))kr(e)}var Cl=5e3,Sn=200;function Ml(n){return n.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}function Ll(n,e,t=Cl){let r=[];if(!e)return{starts:r,capped:!1};let a=new RegExp(Ml(e),"gi"),s;for(;(s=a.exec(n))!==null;){if(r.length===t)return{starts:r,capped:!0};r.push(s.index),s[0].length===0&&(a.lastIndex+=1)}return{starts:r,capped:!1}}var Xt=class{constructor(e,t={}){this.root=e,this.skip=t.skip??"",this.matches=[],this.current=-1}run(e){this.clear();let t=e.slice(0,Sn);if(!t)return{total:0,capped:!1};ws(this.root);let{nodes:r,starts:a,text:s}=this.collectText(),{starts:i,capped:o}=Ll(s,t),c=i.map(()=>[]);for(let u=i.length-1;u>=0;u-=1){let h=i[u],b=h+t.length,m=Rl(a,b-1);for(;m>=0&&a[m]+(r[m].nodeValue??"").length>h;){let _=a[m],p=Math.max(h,_)-_,g=Math.min(b,_+(r[m].nodeValue??"").length)-_;g>p&&c[u].unshift(Ol(r[m],p,g,u)),m-=1}}return this.matches=c,{total:c.length,capped:o}}collectText(){let e=this.skip,t=document.createTreeWalker(this.root,NodeFilter.SHOW_TEXT,{acceptNode(o){let c=o.parentElement;return e&&c&&c.closest(e)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT}}),r=[],a=[],s=[],i=0;for(let o=t.nextNode();o;o=t.nextNode()){let c=o.nodeValue??"";c&&(r.push(o),a.push(i),s.push(c),i+=c.length)}return{nodes:r,starts:a,text:s.join("")}}go(e){if(!this.matches.length)return null;let t=this.matches.length,r=(e%t+t)%t;for(let a of this.matches[this.current]??[])a.classList.remove("current");this.current=r;for(let a of this.matches[r])a.classList.add("current");return this.matches[r][0]??null}unsetCurrent(){for(let e of this.matches[this.current]??[])e.classList.remove("current");this.current=-1}clear(){let e=new Set;for(let t of this.matches)for(let r of t){let a=r.parentNode;a&&(r.replaceWith(...Array.from(r.childNodes)),e.add(a))}for(let t of e)t.normalize();this.matches=[],this.current=-1}};function Rl(n,e){let t=0,r=n.length-1;for(;t<r;){let a=t+r+1>>1;n[a]<=e?t=a:r=a-1}return t}function Ol(n,e,t,r){let a=n.splitText(e);a.splitText(t-e);let s=document.createElement("mark");return s.className="match",s.setAttribute("part","match"),s.dataset.match=String(r),a.replaceWith(s),s.appendChild(a),s}function de(n){let e=f("button",{class:"btn",part:`button${n.part?` ${n.part}`:""}`,attrs:{type:"button","aria-label":n.label,title:n.label,"aria-pressed":n.pressed===void 0?null:String(n.pressed),"data-focus-key":n.key},on:{click:n.onClick}});return e.append(Pe(n.icon)),e}function As(n,e,t){let r=n.querySelector("svg");r&&(r.replaceWith(Pe(t?"check":"alert")),n.classList.toggle("done",t),setTimeout(()=>{n.querySelector("svg")?.replaceWith(Pe(e)),n.classList.remove("done")},1500))}var Tn=class{constructor(e,t,r=""){this.t=e,this.handlers=t,this.total=0,this.capped=!1,this.index=-1;let a=_e("search");this.input=f("input",{class:"search-input",part:"search-input",attrs:{id:a,type:"search",placeholder:e("searchPlaceholder"),"aria-label":e("search"),maxlength:Sn,autocomplete:"off",spellcheck:"false",enterkeyhint:"search","data-focus-key":"search-input"}}),this.input.value=r.slice(0,Sn),this.count=f("span",{class:"search-count",part:"search-count",attrs:{"aria-hidden":"true"}});let s=de({icon:"chevron-up",label:e("searchPrevious"),onClick:()=>this.step(-1),key:"search-prev"}),i=de({icon:"chevron-down",label:e("searchNext"),onClick:()=>this.step(1),key:"search-next"}),o=de({icon:"close",label:e("searchClose"),onClick:()=>t.onClose(),key:"search-close"});this.element=f("div",{class:"search",part:"search",attrs:{role:"search"}},this.input,this.count,s,i,o);let c=qa(()=>this.run(),150);this.input.addEventListener("input",c),this.input.addEventListener("keydown",u=>{u.key==="Enter"?(u.preventDefault(),c.cancel(),this.input.value!==this.lastQuery?this.run():this.step(u.shiftKey?-1:1)):u.key==="Escape"&&(u.preventDefault(),u.stopPropagation(),this.input.value?(this.input.value="",this.run()):t.onClose())}),this.lastQuery=void 0}run(){let e=this.input.value;this.lastQuery=e;let{total:t,capped:r}=this.handlers.run(e);this.total=t,this.capped=r,this.index=-1,t>0?this.step(1):this.updateCount(),this.handlers.onResult?.(e,t,r)}step(e){this.total&&(this.index=((this.index+e)%this.total+this.total)%this.total,this.handlers.go(this.index),this.updateCount())}updateCount(){if(!this.input.value)this.count.textContent="";else if(!this.total)this.count.textContent=this.t("searchNone");else{let e=this.capped?"searchCountCapped":"searchCount";this.count.textContent=this.t(e,{current:this.index+1,total:this.total})}}focus(){this.input.focus(),this.input.select()}};function Ss({tabs:n,selected:e,label:t,onSelect:r,panelId:a}){let s=f("div",{class:"tabs",part:"tabs",attrs:{role:"tablist","aria-label":t}}),i=n.map(o=>{let c=o.id===e;return f("button",{class:"tab",part:c?"tab tab-active":"tab",attrs:{type:"button",role:"tab","aria-selected":String(c),"aria-controls":a,tabindex:c?"0":"-1","data-tab":o.id,"data-focus-key":`tab-${o.id}`},on:{click:()=>r(o.id)}},o.icon?Pe(o.icon):null,o.label)});return s.append(...i),s.addEventListener("keydown",o=>{let c=i.findIndex(h=>h===o.target);if(c<0)return;let u=-1;o.key==="ArrowRight"?u=(c+1)%i.length:o.key==="ArrowLeft"?u=(c-1+i.length)%i.length:o.key==="Home"?u=0:o.key==="End"&&(u=i.length-1),!(u<0)&&(o.preventDefault(),r(n[u].id))}),s}function Pt(n){return f("div",{class:"loader",part:"loading",attrs:{role:"status"}},Il(),f("span",{class:"loader-label",text:n("loading")}))}var Es="http://www.w3.org/2000/svg";function Il(){let n=document.createElementNS(Es,"svg");n.setAttribute("viewBox","0 0 120 120"),n.setAttribute("class","loader-mark"),n.setAttribute("aria-hidden","true"),n.setAttribute("focusable","false");let e=[["rect",{class:"loader-frame",x:"12",y:"16",width:"96",height:"88",rx:"18"}],["path",{class:"loader-frame",d:"M12 42 L108 42"}],["circle",{class:"loader-dot",cx:"29",cy:"29",r:"5"}],["path",{class:"loader-v",d:"M42 60 L60 86 L78 60",pathLength:"100"}]];for(let[t,r]of e){let a=document.createElementNS(Es,t);for(let[s,i]of Object.entries(r))a.setAttribute(s,i);n.append(a)}return n}function Ts(n,e){return f("div",{class:"message",part:"error",attrs:{role:"alert"}},Pe("alert"),f("div",{},f("p",{class:"message-title",text:n}),e?f("p",{class:"message-detail",text:e}):null))}function Fe(n){return f("div",{class:"notice",part:"notice",attrs:{role:"note"}},Pe("alert"),f("span",{text:n}))}function ks(n){return f("div",{class:"empty",part:"empty",text:n("empty")})}var Ns=new Map;function kn(n){let e=Ns.get(n);return e||(e=new CSSStyleSheet,e.replaceSync(n),Ns.set(n,e)),e}var Dl=Object.freeze(["variant","theme","src","allow-remote","max-height","copy","search","download","header","dot","title","label","lang-ui","mode","edit-toggle","placeholder","syntax-theme","syntax-theme-dark","badge","history","fullscreen","status","json","json-src","json-path"]);function Pl(n){return n instanceof HTMLTemplateElement?n.content.textContent??"":n.textContent??""}var $e=class extends HTMLElement{static type="base";static componentAttributes=[];static presets={simple:{},full:{}};static allowEmpty=!1;static keepCarriageReturns=!1;static dataAttributes=[];static fromData(e){return typeof e=="string"?e:Wt(e)}static upgradeProperties=["content"];static styles=[];static get observedAttributes(){return[...Dl,...this.componentAttributes]}constructor(){super(),this.root=this.attachShadow({mode:"open"}),this.frame=f("div",{class:"vt",part:"container"}),this.syntaxTheme=null,this.updateSheets(null),this.live=f("div",{class:"sr-only",attrs:{"aria-live":"polite","aria-atomic":"true"}}),this.root.append(this.frame,this.live),this._content=void 0,this._data=void 0,this._fromJson=!1,this._dataAttributes=new Set,this.text=null,this.error=null,this.loading=!1,this.searchOpen=!1,this.searchQuery="",this.searchBar=null,this.t=wr("en"),this._loadToken=0,this._abort=null,this._renderQueued=!1,this._readyPending=!1,this._cleanups=[],this._observer=null,this._connected=!1,this.modeState=null,this.editHistory=null,this._historyCleanup=null,this._escapeFullscreen=null}get content(){return this.text??""}set content(e){let t=e==null?void 0:String(e);t!==void 0&&t===this._content&&t===this.text||(this._content=t,this._fromJson=!1,this._connected&&this.reload())}get data(){return this._data}set data(e){this._fromJson=!1,this.applyData(e)}applyData(e){this._data=e;let t=this.constructor,r;try{r=t.fromData(e)}catch(i){this._content="",this.setError(new ue("jsonUnusable",{},i));return}let{content:a,attributes:s={}}=typeof r=="string"?{content:r}:r;this.applyDataAttributes(s),this._content=a,this._connected&&this.setText(a)}applyDataAttributes(e){let t=this.constructor.dataAttributes,r=this._dataAttributes;this._dataAttributes=new Set;for(let[a,s]of Object.entries(e)){if(!t.includes(a)||s===null||s===void 0||this.hasAttribute(a)&&!r.has(a))continue;let i=s===!0?"":s===!1?"false":String(s).slice(0,2e3);this.getAttribute(a)!==i&&this.setAttribute(a,i),this._dataAttributes.add(a)}for(let a of r)this._dataAttributes.has(a)||this.removeAttribute(a)}loadJson(){let e=this.getAttribute("json-src")?.trim(),t=this.getAttribute("json"),r=this.querySelector(":scope > script[data-json], :scope > template[data-json]");if(!e&&t===null&&!r)return this._fromJson&&(this._fromJson=!1,this._content=void 0),!1;let a=++this._loadToken;if(this._abort?.abort(),this._abort=null,!e)return this.useJson(t??Pl(r)),!0;let s=W();this.loading=!0,this.error=null,this.requestRender();let i=new AbortController;return this._abort=i,yr(e,{allowRemote:Ie(this.getAttribute("allow-remote"))===!0,maxSize:s.maxSize,timeout:s.fetchTimeout,signal:i.signal}).then(o=>a===this._loadToken&&this.useJson(o),o=>a===this._loadToken&&!vr(o)&&this.setError(o)),!0}useJson(e){this.loading=!1;let t;try{Kt(e,W().maxSize),t=JSON.parse(e)}catch(a){this.setError(a instanceof ue?a:new ue("jsonInvalid",{message:a instanceof Error?a.message:""},a));return}let r=this.getAttribute("json-path")?.trim();if(r){let a=Qa(t,r);if(!a.ok){this.setError(new ue("jsonPathMissing",{path:r.slice(0,100)}));return}t=a.value}this._fromJson=!0,this.applyData(t)}upgradeProperty(e){if(Object.prototype.hasOwnProperty.call(this,e)){let t=this[e];delete this[e],this[e]=t}}connectedCallback(){for(let t of new Set([...this.constructor.upgradeProperties,"data"]))this.upgradeProperty(t);this._cleanups.push(Ga(t=>t.has("maxSize")?this.reload():this.requestRender()),ds(()=>this.applyTheme()),as(()=>this.requestRender())),this._observer=new MutationObserver(()=>{(this._content===void 0||this._fromJson)&&!this.hasAttribute("src")&&this.reload()}),this._observer.observe(this,{childList:!0,characterData:!0,subtree:!0});let e=()=>{document.fullscreenElement===this?this.setFullscreen("native"):this.frame.dataset.fullscreen==="native"&&this.setFullscreen(null)};document.addEventListener("fullscreenchange",e),this._cleanups.push(()=>document.removeEventListener("fullscreenchange",e)),this._connected=!0,this.reload()}disconnectedCallback(){this._connected=!1;for(let e of this._cleanups.splice(0))e();this._observer?.disconnect(),this._observer=null,this._abort?.abort(),this._abort=null}attributeChangedCallback(e,t,r){t===r||!this.isConnected||(e==="mode"&&(this.modeState=null),["src","allow-remote","json","json-src","json-path"].includes(e)?this.reload():e==="theme"?this.applyTheme():this.requestRender())}reload(){if((this._content===void 0||this._fromJson)&&this.loadJson())return;let e=++this._loadToken;this._abort?.abort(),this._abort=null;let t=W(),r=this.getAttribute("src");if(this._content!==void 0)this.setText(this._content);else if(r!==null&&r.trim()!==""){this.loading=!0,this.error=null,this.requestRender();let a=new AbortController;this._abort=a,yr(r,{allowRemote:Ie(this.getAttribute("allow-remote"))===!0,maxSize:t.maxSize,timeout:t.fetchTimeout,signal:a.signal}).then(s=>e===this._loadToken&&this.setText(s),s=>e===this._loadToken&&!vr(s)&&this.setError(s))}else this.setText(this.readInline()??"")}setText(e){this.loading=!1,this.editHistory=null;try{Kt(e,W().maxSize)}catch(r){this.setError(r);return}let t=this.constructor;this.text=e.replace(t.keepCarriageReturns?/\r\n/g:/\r\n?/g,`
`),this.error=null,this.contentChanged(),this._readyPending=!0,this.requestRender()}setError(e){this.loading=!1,this._readyPending=!1,this.error=e,this.text=null,this.contentChanged(),this.requestRender();let{title:t,detail:r}=this.describeError(e);ne(this,te.ERROR,{message:r||t,cause:e})}describeError(e){let t=this.t;if(e instanceof ue){let r={...e.params};for(let a of["size","limit"])typeof r[a]=="number"&&(r[a]=dt(Number(r[a]),this.locale));return{title:t("errorTitle"),detail:t(e.code,r)}}return{title:t("errorTitle"),detail:e instanceof Error?e.message:String(e)}}get editing(){return(this.modeState??Ot(this.getAttribute("mode"),["view","edit"],"view"))==="edit"}edited(e){this.text=e,this._content=e,this.contentEdited(e),ne(this,te.INPUT,{value:e})}contentEdited(e){}historyButtons(e){if(this.editHistory=e.history,Ie(this.getAttribute("history"))===!1)return[];let t=de({icon:"undo",label:this.t("undo"),key:"undo",part:"undo-button",onClick:()=>e.undo()}),r=de({icon:"redo",label:this.t("redo"),key:"redo",part:"redo-button",onClick:()=>e.redo()}),a=()=>{t.disabled=!e.history.canUndo,r.disabled=!e.history.canRedo};return a(),this._historyCleanup?.(),this._historyCleanup=e.history.subscribe(a),[t,r]}fullscreenButton(){if(!this.feature("fullscreen"))return null;let e=!!this.frame.dataset.fullscreen;return de({icon:e?"minimize":"maximize",label:this.t(e?"exitFullscreen":"fullscreen"),key:"fullscreen",part:"fullscreen-button",pressed:e,onClick:()=>this.toggleFullscreen()})}async toggleFullscreen(){let e=this.frame.dataset.fullscreen;if(e==="native"){await document.exitFullscreen?.().catch(()=>{});return}if(e==="window"){this.setFullscreen(null);return}if(document.fullscreenEnabled&&this.requestFullscreen)try{await this.requestFullscreen({navigationUI:"hide"});return}catch{}this.setFullscreen("window")}setFullscreen(e){e?this.frame.dataset.fullscreen=e:delete this.frame.dataset.fullscreen,e==="window"?(this._escapeFullscreen=t=>{t.key==="Escape"&&!t.defaultPrevented&&this.setFullscreen(null)},this.frame.addEventListener("keydown",this._escapeFullscreen)):this._escapeFullscreen&&(this.frame.removeEventListener("keydown",this._escapeFullscreen),this._escapeFullscreen=null),this.render(),this.root.querySelector('[data-focus-key="fullscreen"]')?.focus(),ne(this,te.FULLSCREEN_CHANGE,{fullscreen:!!e})}editToggleButton(){return this.feature("edit-toggle")?de({icon:this.editing?"eye":"pencil",label:this.t(this.editing?"stopEditing":"edit"),key:"edit-toggle",part:"edit-button",pressed:this.editing,onClick:()=>{this.modeState=this.editing?"view":"edit",this.render(),ne(this,te.MODE_CHANGE,{mode:this.modeState}),this.modeState==="edit"&&this.root.querySelector(".editor-input")?.focus()}}):null}readInline(){return Ya(this)}contentChanged(){}get variant(){return Ot(this.getAttribute("variant"),["simple","full"],"simple")}feature(e){let t=Ie(this.getAttribute(e));return t!==null?t:this.constructor.presets[this.variant][e]??!1}get locale(){let e=this.getAttribute("lang-ui")?.trim();return e&&/^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(e)?e:W().lang}get heading(){return Ba(this.getAttribute("label")??this.getAttribute("title"))}requestRender(){this._renderQueued||(this._renderQueued=!0,queueMicrotask(()=>{this._renderQueued=!1,this.isConnected&&this.render()}))}applyTheme(){let e=hs(this.getAttribute("theme"));this.frame.dataset.theme=e,this.applySyntaxTheme(us(e)?.colorScheme==="dark")}applySyntaxTheme(e){let t=W(),r=e&&this.getAttribute("syntax-theme-dark")||this.getAttribute("syntax-theme")||e&&t.syntaxThemeDark||t.syntaxTheme,a=bs(r);if(this.syntaxTheme=a,!a){this.updateSheets(null);return}let s=ys(a);if(s){this.updateSheets(s);return}vs(a).then(i=>{i&&this.syntaxTheme===a&&this.updateSheets(i)})}updateSheets(e){let r=this.constructor.styles.map(kn),a=[kn(ja),ht,kn(Fa),...r];this.frame.toggleAttribute("data-syntax-theme",!!e),this.root.adoptedStyleSheets=e?[...a.filter(s=>s!==kn(tt)),e]:a}render(){let e=this.activeFocusKey(),t=this.root.activeElement,r=t instanceof HTMLTextAreaElement||t instanceof HTMLInputElement?[t.selectionStart,t.selectionEnd]:null;this.t=wr(this.locale),this.applyTheme();let a=za(this.getAttribute("max-height"));if(a?this.frame.style.setProperty("--_max-height",a):this.frame.style.removeProperty("--_max-height"),this.searchBar=null,this.frame.replaceChildren(),this.loading){this.frame.append(...this.chrome(null),f("div",{class:"body",part:"body"},Pt(this.t))),this.frame.setAttribute("aria-busy","true");return}if(this.frame.removeAttribute("aria-busy"),this.error){let{title:i,detail:o}=this.describeError(this.error);this.frame.append(...this.chrome(null),Ts(i,o));return}if(!this.text&&!this.editing&&!this.constructor.allowEmpty)this.frame.append(...this.chrome(null),ks(this.t));else{this.renderContent(this.frame);let i=this.searchBar;this.searchOpen&&this.searchQuery&&i?.run()}this.restoreFocus(e);let s=this.root.activeElement;if(r&&(s instanceof HTMLTextAreaElement||s instanceof HTMLInputElement)&&r[0]!==null)try{s.setSelectionRange(r[0],r[1])}catch{}this._readyPending&&(this._readyPending=!1,ne(this,te.READY,{type:this.constructor.type}))}renderContent(e){throw new Error("renderContent() must be implemented.")}chrome(e){let t=(e?.actions??[]).filter(i=>i!==null),r=t.length?f("div",{class:"toolbar",part:"toolbar",attrs:{role:"toolbar","aria-label":this.t("actions")}},...t):null;if(!this.feature("header"))return r?.classList.add("floating"),[r,e?.tabs??null,this.searchBar?.element??null].filter(i=>i!==null);let a=this.heading,s=f("div",{class:"header",part:"header"},this.feature("dot")?f("span",{class:"dot",part:"status-dot",attrs:{"aria-hidden":"true"}}):null,a?f("span",{class:"title",part:"title",text:a,attrs:{title:a}}):null,e?.tabs??null,a?null:f("span",{class:"spacer"}),e?.badge&&Ie(this.getAttribute("badge"))!==!1?f("span",{class:"badge",part:"badge",text:e.badge}):null);return r&&s.append(r),this.searchBar?[s,this.searchBar.element]:[s]}copyButton(e,t=this.t("copy"),r="copy"){let a=de({icon:"copy",label:t,key:r,part:"copy-button",onClick:async()=>{let s=e(),i=await mr(s,this.root);As(a,"copy",i),this.announce(this.t(i?"copied":"copyFailed")),i&&ne(this,te.COPY,{text:s})}});return a}copyTextButton(e,t,r){let a=f("button",{class:"text-btn",part:"copy-button",text:t,attrs:{type:"button","data-focus-key":r},on:{click:async()=>{let s=e(),i=await mr(s,this.root);a.textContent=this.t(i?"copied":"copyFailed"),a.classList.toggle("done",i),setTimeout(()=>{a.textContent=t,a.classList.remove("done")},1500),this.announce(this.t(i?"copied":"copyFailed")),i&&ne(this,te.COPY,{text:s})}}});return a}downloadName(e){let t=this.getAttribute("download"),r=t&&Ie(t)!==!1&&!/^(?:true|on|yes)$/i.test(t.trim())?t:null,a=/\.[a-z0-9]{1,10}$/i.test(this.heading)?this.heading:null;return Ua(r??a,e)}downloadButton(e,t,r){return de({icon:"download",label:this.t("download"),key:"download",part:"download-button",onClick:()=>$a(e(),t,r)})}searchButton(e){return this.feature("search")?(this.searchOpen&&(this.searchBar=new Tn(this.t,{run:t=>(this.searchQuery=t,e.run(t)),go:t=>e.go(t),onResult:(t,r,a)=>{t&&this.announce(r?this.t("searchResults",{total:a?`${r}+`:r}):this.t("searchNone")),ne(this,te.SEARCH,{query:t,matches:r})},onClose:()=>{e.clear(),this.searchOpen=!1,this.searchQuery="",this.render(),this.root.querySelector('[data-focus-key="search"]')?.focus()}},this.searchQuery)),de({icon:"search",label:this.t("search"),key:"search",part:"search-button",pressed:this.searchOpen,onClick:()=>{this.searchOpen=!this.searchOpen,this.searchOpen||(this.searchQuery=""),this.render(),this.searchOpen&&this.searchBar?.focus()}})):null}announce(e){this.live.textContent="",setTimeout(()=>{this.live.textContent=e},50)}activeFocusKey(){let e=this.root.activeElement;return e instanceof HTMLElement?e.dataset.focusKey??null:null}restoreFocus(e){if(!e)return;let t=this.root.querySelector(`[data-focus-key="${CSS.escape(e)}"]`);t instanceof HTMLElement&&t.focus({preventScroll:!0})}};var Ys=Zo(Ws(),1);var He=Ys.default;function Zs(n){let e=n.regex,t={},r={begin:/\$\{/,end:/\}/,contains:["self",{begin:/:-/,contains:[t]}]};Object.assign(t,{className:"variable",variants:[{begin:e.concat(/\$[\w\d#@][\w\d_]*/,"(?![\\w\\d])(?![$])")},r]});let a={className:"subst",begin:/\$\(/,end:/\)/,contains:[n.BACKSLASH_ESCAPE]},s=n.inherit(n.COMMENT(),{match:[/(^|\s)/,/#.*$/],scope:{2:"comment"}}),i={begin:/<<-?\s*(?=\w+)/,starts:{contains:[n.END_SAME_AS_BEGIN({begin:/(\w+)/,end:/(\w+)/,className:"string"})]}},o={className:"string",begin:/"/,end:/"/,contains:[n.BACKSLASH_ESCAPE,t,a]};a.contains.push(o);let c={match:/\\"/},u={className:"string",begin:/'/,end:/'/},h={match:/\\'/},b={begin:/\$?\(\(/,end:/\)\)/,contains:[{begin:/\d+#[0-9a-f]+/,className:"number"},n.NUMBER_MODE,t]},m=["fish","bash","zsh","sh","csh","ksh","tcsh","dash","scsh"],_=n.SHEBANG({binary:`(${m.join("|")})`,relevance:10}),p={className:"function",begin:/\w[\w\d_]*\s*\(\s*\)\s*\{/,returnBegin:!0,contains:[n.inherit(n.TITLE_MODE,{begin:/\w[\w\d_]*/})],relevance:0},g=["if","then","else","elif","fi","time","for","while","until","in","do","done","case","esac","coproc","function","select"],S=["true","false"],M={match:/(\/[a-z._-]+)+/},D=["break","cd","continue","eval","exec","exit","export","getopts","hash","pwd","readonly","return","shift","test","times","trap","umask","unset"],j=["alias","bind","builtin","caller","command","declare","echo","enable","help","let","local","logout","mapfile","printf","read","readarray","source","sudo","type","typeset","ulimit","unalias"],P=["autoload","bg","bindkey","bye","cap","chdir","clone","comparguments","compcall","compctl","compdescribe","compfiles","compgroups","compquote","comptags","comptry","compvalues","dirs","disable","disown","echotc","echoti","emulate","fc","fg","float","functions","getcap","getln","history","integer","jobs","kill","limit","log","noglob","popd","print","pushd","pushln","rehash","sched","setcap","setopt","stat","suspend","ttyctl","unfunction","unhash","unlimit","unsetopt","vared","wait","whence","where","which","zcompile","zformat","zftp","zle","zmodload","zparseopts","zprof","zpty","zregexparse","zsocket","zstyle","ztcp"],q=["chcon","chgrp","chown","chmod","cp","dd","df","dir","dircolors","ln","ls","mkdir","mkfifo","mknod","mktemp","mv","realpath","rm","rmdir","shred","sync","touch","truncate","vdir","b2sum","base32","base64","cat","cksum","comm","csplit","cut","expand","fmt","fold","head","join","md5sum","nl","numfmt","od","paste","ptx","pr","sha1sum","sha224sum","sha256sum","sha384sum","sha512sum","shuf","sort","split","sum","tac","tail","tr","tsort","unexpand","uniq","wc","arch","basename","chroot","date","dirname","du","echo","env","expr","factor","groups","hostid","id","link","logname","nice","nohup","nproc","pathchk","pinky","printenv","printf","pwd","readlink","runcon","seq","sleep","stat","stdbuf","stty","tee","test","timeout","tty","uname","unlink","uptime","users","who","whoami","yes"];return{name:"Bash",aliases:["sh","zsh"],keywords:{$pattern:/\b[a-z][a-z0-9._-]+\b/,keyword:g,literal:S,built_in:[...D,...j,"set","shopt",...P,...q]},contains:[_,n.SHEBANG(),p,b,s,i,M,o,c,u,h,t]}}function Js(n){let e=n.regex;return{name:"Diff",aliases:["patch"],contains:[{className:"meta",relevance:10,match:e.either(/^@@ +-\d+,\d+ +\+\d+,\d+ +@@/,/^@@ +-\d+ +\+\d+,\d+ +@@/,/^@@ +-\d+,\d+ +\+\d+ +@@/,/^@@ +-\d+ +\+\d+ +@@/,/^\*\*\* +\d+,\d+ +\*\*\*\*$/,/^--- +\d+,\d+ +----$/)},{className:"comment",variants:[{begin:e.either(/Index: /,/^index/,/={3,}/,/^-{3}/,/^\*{3} /,/^\+{3}/,/^diff --git/),end:/$/},{match:/^\*{15}$/}]},{className:"addition",begin:/^\+/,end:/$/},{className:"deletion",begin:/^-/,end:/$/},{className:"addition",begin:/^!/,end:/$/}]}}var Xs="[A-Za-z$_][0-9A-Za-z$_]*",Tc=["as","in","of","if","for","while","finally","var","new","function","do","return","void","else","break","catch","instanceof","with","throw","case","default","try","switch","continue","typeof","delete","let","yield","const","class","debugger","async","await","static","import","from","export","extends","using"],kc=["true","false","null","undefined","NaN","Infinity"],Qs=["Object","Function","Boolean","Symbol","Math","Date","Number","BigInt","String","RegExp","Array","Float32Array","Float64Array","Int8Array","Uint8Array","Uint8ClampedArray","Int16Array","Int32Array","Uint16Array","Uint32Array","BigInt64Array","BigUint64Array","Set","Map","WeakSet","WeakMap","ArrayBuffer","SharedArrayBuffer","Atomics","DataView","JSON","Promise","Generator","GeneratorFunction","AsyncFunction","Reflect","Proxy","Intl","WebAssembly"],ei=["Error","EvalError","InternalError","RangeError","ReferenceError","SyntaxError","TypeError","URIError"],ti=["setInterval","setTimeout","clearInterval","clearTimeout","require","exports","eval","isFinite","isNaN","parseFloat","parseInt","decodeURI","decodeURIComponent","encodeURI","encodeURIComponent","escape","unescape"],Nc=["arguments","this","super","console","window","document","localStorage","sessionStorage","module","self","global"],Cc=[].concat(ti,Qs,ei);function ni(n){let e=n.regex,t=(R,{after:F})=>{let E="</"+R[0].slice(1);return R.input.indexOf(E,F)!==-1},r=Xs,a={begin:"<>",end:"</>"},s=/<[A-Za-z0-9\\._:-]+\s*\/>/,i={begin:/<[A-Za-z0-9\\._:-]+/,end:/\/[A-Za-z0-9\\._:-]+>|\/>/,isTrulyOpeningTag:(R,F)=>{let E=R[0].length+R.index,L=R.input[E];if(L==="<"||L===","){F.ignoreMatch();return}L===">"&&(t(R,{after:E})||F.ignoreMatch());let z,Y=R.input.substring(E);if(z=Y.match(/^\s*=/)){F.ignoreMatch();return}if((z=Y.match(/^\s+extends\s+/))&&z.index===0){F.ignoreMatch();return}}},o={$pattern:Xs,keyword:Tc,literal:kc,built_in:Cc,"variable.language":Nc},c="[0-9](_?[0-9])*",u=`\\.(${c})`,h="0|[1-9](_?[0-9])*|0[0-7]*[89][0-9]*",b={className:"number",variants:[{begin:`(\\b(${h})((${u})|\\.)?|(${u}))[eE][+-]?(${c})\\b`},{begin:`\\b(${h})\\b((${u})\\b|\\.)?|(${u})\\b`},{begin:"\\b(0|[1-9](_?[0-9])*)n\\b"},{begin:"\\b0[xX][0-9a-fA-F](_?[0-9a-fA-F])*n?\\b"},{begin:"\\b0[bB][0-1](_?[0-1])*n?\\b"},{begin:"\\b0[oO][0-7](_?[0-7])*n?\\b"},{begin:"\\b0[0-7]+n?\\b"}],relevance:0},m={className:"subst",begin:"\\$\\{",end:"\\}",keywords:o,contains:[]},_={begin:".?html`",end:"",starts:{end:"`",returnEnd:!1,contains:[n.BACKSLASH_ESCAPE,m],subLanguage:"xml"}},p={begin:".?css`",end:"",starts:{end:"`",returnEnd:!1,contains:[n.BACKSLASH_ESCAPE,m],subLanguage:"css"}},g={begin:".?gql`",end:"",starts:{end:"`",returnEnd:!1,contains:[n.BACKSLASH_ESCAPE,m],subLanguage:"graphql"}},S={className:"string",begin:"`",end:"`",contains:[n.BACKSLASH_ESCAPE,m]},D={className:"comment",variants:[n.COMMENT(/\/\*\*(?!\/)/,"\\*/",{relevance:0,contains:[{begin:"(?=@[A-Za-z]+)",relevance:0,contains:[{className:"doctag",begin:"@[A-Za-z]+"},{className:"type",begin:"\\{",end:"\\}",excludeEnd:!0,excludeBegin:!0,relevance:0},{className:"variable",begin:r+"(?=\\s*(-)|$)",endsParent:!0,relevance:0},{begin:/(?=[^\n])\s/,relevance:0}]}]}),n.C_BLOCK_COMMENT_MODE,n.C_LINE_COMMENT_MODE]},j=[n.APOS_STRING_MODE,n.QUOTE_STRING_MODE,_,p,g,S,{match:/\$\d+/},b];m.contains=j.concat({begin:/\{/,end:/\}/,keywords:o,contains:["self"].concat(j)});let P=[].concat(D,m.contains),q=P.concat([{begin:/(\s*)\(/,end:/\)/,keywords:o,contains:["self"].concat(P)}]),X={className:"params",begin:/(\s*)\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:o,contains:q},ae={variants:[{match:[/class/,/\s+/,r,/\s+/,/extends/,/\s+/,e.concat(r,"(",e.concat(/\./,r),")*")],scope:{1:"keyword",3:"title.class",5:"keyword",7:"title.class.inherited"}},{match:[/class/,/\s+/,r],scope:{1:"keyword",3:"title.class"}}]},ie={relevance:0,match:e.either(/\bJSON/,/\b[A-Z][a-z]+([A-Z][a-z]*|\d)*/,/\b[A-Z]{2,}([A-Z][a-z]+|\d)+([A-Z][a-z]*)*/,/\b[A-Z]{2,}[a-z]+([A-Z][a-z]+|\d)*([A-Z][a-z]*)*/),className:"title.class",keywords:{_:[...Qs,...ei]}},Le={label:"use_strict",className:"meta",relevance:10,begin:/^\s*['"]use (strict|asm)['"]/},ke={variants:[{match:[/function/,/\s+/,r,/(?=\s*\()/]},{match:[/function/,/\s*(?=\()/]}],className:{1:"keyword",3:"title.function"},label:"func.def",contains:[X],illegal:/%/},se={relevance:0,match:/\b[A-Z][A-Z_0-9]+\b/,className:"variable.constant"};function ye(R){return e.concat("(?!",R.join("|"),")")}let Be={match:e.concat(/\b/,ye([...ti,"super","import","await"].map(R=>`${R}\\s*\\(`)),r,e.lookahead(/\s*\(/)),className:"title.function",relevance:0},Ne={begin:e.concat(/\./,e.lookahead(e.concat(r,/(?![0-9A-Za-z$_(])/))),end:r,excludeBegin:!0,keywords:"prototype",className:"property",relevance:0},Re={match:[/get|set/,/\s+/,r,/(?=\()/],className:{1:"keyword",3:"title.function"},contains:[{begin:/\(\)/},X]},w="(\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)|"+n.UNDERSCORE_IDENT_RE+")\\s*=>",k={match:[/const|var|let/,/\s+/,r,/\s*/,/=\s*/,/(async\s*)?/,e.lookahead(w)],keywords:"async",className:{1:"keyword",3:"title.function"},contains:[X]};return{name:"JavaScript",aliases:["js","jsx","mjs","cjs"],keywords:o,exports:{PARAMS_CONTAINS:q,CLASS_REFERENCE:ie},illegal:/#(?![$_A-Za-z])/,contains:[n.SHEBANG({label:"shebang",binary:"node",relevance:5}),Le,n.APOS_STRING_MODE,n.QUOTE_STRING_MODE,_,p,g,S,D,{match:/\$\d+/},b,ie,{scope:"attr",match:r+e.lookahead(":"),relevance:0},k,{begin:"("+n.RE_STARTERS_RE+"|\\b(case|return|throw)\\b)\\s*",keywords:"return throw case",relevance:0,contains:[D,n.REGEXP_MODE,{className:"function",begin:w,returnBegin:!0,end:"\\s*=>",contains:[{className:"params",variants:[{begin:n.UNDERSCORE_IDENT_RE,relevance:0},{className:null,begin:/\(\s*\)/,skip:!0},{begin:/(\s*)\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:o,contains:q}]}]},{begin:/,/,relevance:0},{match:/\s+/,relevance:0},{variants:[{begin:a.begin,end:a.end},{match:s},{begin:i.begin,"on:begin":i.isTrulyOpeningTag,end:i.end}],subLanguage:"xml",contains:[{begin:i.begin,end:i.end,skip:!0,contains:["self"]}]}]},ke,{beginKeywords:"while if switch catch for"},{begin:"\\b(?!function)"+n.UNDERSCORE_IDENT_RE+"\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)\\s*\\{",returnBegin:!0,label:"func.def",contains:[X,n.inherit(n.TITLE_MODE,{begin:r,className:"title.function"})]},{match:/\.\.\./,relevance:0},Ne,{match:"\\$"+r,relevance:0},{match:[/\bconstructor(?=\s*\()/],className:{1:"title.function"},contains:[X]},Be,se,ae,Re,{match:/\$[(.]/}]}}var Mc="([-+]?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)|NaN|[-+]?Infinity",Lc={scope:"number",match:Mc,relevance:0};function ri(n){let e={className:"attr",begin:/(("(\\.|[^\\"\r\n])*")|('(\\.|[^\\'\r\n])*'))(?=\s*:)/,relevance:1.01},t={match:/[{}[\],:]/,className:"punctuation",relevance:0},r=["true","false","null"],a={scope:"literal",beginKeywords:r.join(" ")};return{name:"JSON",aliases:["jsonc","json5"],keywords:{literal:r},contains:[e,t,n.APOS_STRING_MODE,n.QUOTE_STRING_MODE,a,Lc,n.C_LINE_COMMENT_MODE,n.C_BLOCK_COMMENT_MODE],illegal:"\\S"}}function ai(n){let e=n.regex,t={begin:/<\/?[A-Za-z_]/,end:">",subLanguage:"xml",relevance:0},r={match:/^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/},a={className:"code",variants:[{begin:"(`{3,})[^`](.|\\n)*?\\1`*[ ]*"},{begin:"(~{3,})[^~](.|\\n)*?\\1~*[ ]*"},{begin:"```",end:"```+[ ]*$"},{begin:"~~~",end:"~~~+[ ]*$"},{begin:"`.+?`"},{begin:"(?=^( {4}|\\t))",contains:[{begin:"^( {4}|\\t)",end:"(\\n)$"}],relevance:0}]},s={className:"bullet",begin:"^[ 	]*([*+-]|(\\d+\\.))(?=\\s+)",end:"\\s+",excludeEnd:!0},i={begin:/^\[[^\n]+\]:/,returnBegin:!0,contains:[{className:"symbol",begin:/\[/,end:/\]/,excludeBegin:!0,excludeEnd:!0},{className:"link",begin:/:\s*/,end:/$/,excludeBegin:!0}]},o=/[A-Za-z][A-Za-z0-9+.-]*/,c={variants:[{begin:/\[.+?\]\[.*?\]/,relevance:0},{begin:/\[.+?\]\(((data|javascript|mailto):|(?:http|ftp)s?:\/\/).*?\)/,relevance:2},{begin:e.concat(/\[.+?\]\(/,o,/:\/\/.*?\)/),relevance:2},{begin:/\[.+?\]\([./?&#].*?\)/,relevance:1},{begin:/\[.*?\]\(.*?\)/,relevance:0}],returnBegin:!0,contains:[{match:/\[(?=\])/},{className:"string",relevance:0,begin:"\\[",end:"\\]",excludeBegin:!0,returnEnd:!0},{className:"link",relevance:0,begin:"\\]\\(",end:"\\)",excludeBegin:!0,excludeEnd:!0},{className:"symbol",relevance:0,begin:"\\]\\[",end:"\\]",excludeBegin:!0,excludeEnd:!0}]},u={className:"strong",contains:[],variants:[{begin:/_{2}(?!\s)/,end:/_{2}/},{begin:/\*{2}(?!\s)/,end:/\*{2}/}]},h={className:"emphasis",contains:[],variants:[{begin:/\*(?![*\s])/,end:/\*/},{begin:/_(?![_\s])/,end:/_/,relevance:0}]},b=n.inherit(u,{contains:[]}),m=n.inherit(h,{contains:[]});u.contains.push(m),h.contains.push(b);let _=[t,c];return[u,h,b,m].forEach(M=>{M.contains=M.contains.concat(_)}),_=_.concat(u,h),{name:"Markdown",aliases:["md","mkdown","mkd"],contains:[{className:"section",variants:[{begin:"^#{1,6}",end:"$",contains:_},{begin:"(?=^.+?\\n[=-]{2,}$)",contains:[{begin:"^[=-]*$"},{begin:"^",end:"\\n",contains:_}]}]},t,s,r,u,h,{className:"quote",begin:"^>\\s+",contains:_,end:"$"},a,c,i,{scope:"literal",match:/&([a-zA-Z0-9]+|#[0-9]{1,7}|#[Xx][0-9a-fA-F]{1,6});/}]}}function si(n){return{name:"Plain text",aliases:["text","txt"],disableAutodetect:!0}}function ii(n){let e=n.regex,t=/[\p{XID_Start}_]\p{XID_Continue}*/u,r=["and","as","assert","async","await","break","case","class","continue","def","del","elif","else","except","finally","for","from","global","if","import","in","is","lambda","lazy","match","nonlocal|10","not","or","pass","raise","return","try","while","with","yield"],o={$pattern:/[A-Za-z]\w+|__\w+__/,keyword:r,built_in:["__import__","abs","aiter","all","anext","any","ascii","bin","bool","breakpoint","bytearray","bytes","callable","chr","classmethod","compile","complex","delattr","dict","dir","divmod","enumerate","eval","exec","filter","float","format","frozendict","frozenset","getattr","globals","hasattr","hash","help","hex","id","input","int","isinstance","issubclass","iter","len","list","locals","map","max","memoryview","min","next","object","oct","open","ord","pow","print","property","range","repr","reversed","round","sentinel","set","setattr","slice","sorted","staticmethod","str","sum","super","tuple","type","vars","zip"],literal:["__debug__","Ellipsis","False","None","NotImplemented","True"],type:["Any","Callable","Coroutine","Dict","List","Literal","Generic","Optional","Sequence","Set","Tuple","Type","Union"]},c={className:"meta",begin:/^(>>>|\.\.\.) /},u={className:"subst",begin:/\{/,end:/\}/,keywords:o,illegal:/#/},h={begin:/\{\{/,relevance:0},b={className:"string",contains:[n.BACKSLASH_ESCAPE],variants:[{begin:/([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?'''/,end:/'''/,contains:[n.BACKSLASH_ESCAPE,c],relevance:10},{begin:/([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?"""/,end:/"""/,contains:[n.BACKSLASH_ESCAPE,c],relevance:10},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])'''/,end:/'''/,contains:[n.BACKSLASH_ESCAPE,c,h,u]},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])"""/,end:/"""/,contains:[n.BACKSLASH_ESCAPE,c,h,u]},{begin:/([uU]|[rR])'/,end:/'/,relevance:10},{begin:/([uU]|[rR])"/,end:/"/,relevance:10},{begin:/([bB]|[bB][rR]|[rR][bB])'/,end:/'/},{begin:/([bB]|[bB][rR]|[rR][bB])"/,end:/"/},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])'/,end:/'/,contains:[n.BACKSLASH_ESCAPE,h,u]},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])"/,end:/"/,contains:[n.BACKSLASH_ESCAPE,h,u]},n.APOS_STRING_MODE,n.QUOTE_STRING_MODE]},m="[0-9](_?[0-9])*",_=`(\\b(${m}))?\\.(${m})|\\b(${m})\\.`,p=`\\b|${r.join("|")}`,g={className:"number",relevance:0,variants:[{begin:`(\\b(${m})|(${_}))[eE][+-]?(${m})[jJ]?(?=${p})`},{begin:`(${_})[jJ]?`},{begin:`\\b([1-9](_?[0-9])*|0+(_?0)*)[lLjJ]?(?=${p})`},{begin:`\\b0[bB](_?[01])+[lL]?(?=${p})`},{begin:`\\b0[oO](_?[0-7])+[lL]?(?=${p})`},{begin:`\\b0[xX](_?[0-9a-fA-F])+[lL]?(?=${p})`},{begin:`\\b(${m})[jJ](?=${p})`}]},S={className:"comment",begin:e.lookahead(/# type:/),end:/$/,keywords:o,contains:[{begin:/# type:/},{begin:/#/,end:/\b\B/,endsWithParent:!0}]},M={className:"params",variants:[{className:"",begin:/\(\s*\)/,skip:!0},{begin:/\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:o,contains:["self",c,g,b,n.HASH_COMMENT_MODE]}]};return u.contains=[b,g,c],{name:"Python",aliases:["py","gyp","ipython"],unicodeRegex:!0,keywords:o,illegal:/(<\/|\?)|=>/,contains:[c,g,{scope:"variable.language",match:/\bself\b/},{beginKeywords:"if",relevance:0},{match:/\bor\b/,scope:"keyword"},b,S,n.HASH_COMMENT_MODE,{match:[/\bdef/,/\s+/,t],scope:{1:"keyword",3:"title.function"},contains:[M]},{variants:[{match:[/\bclass/,/\s+/,t,/\s*/,/\(\s*/,t,/\s*\)/]},{match:[/\bclass/,/\s+/,t]}],scope:{1:"keyword",3:"title.class",6:"title.class.inherited"}},{className:"meta",begin:/^[\t ]*@/,end:/(?=#)|$/,contains:[g,M,b]}]}}function oi(n){return{name:"Shell Session",aliases:["console","shellsession"],contains:[{className:"meta.prompt",begin:/^\s{0,3}[./~\w\d[\]()@-]*[>%$#][ ]?/,starts:{end:/[^\\](?=\s*$)/,subLanguage:"bash"}}]}}function li(n){let e=n.regex,t=e.concat(/[\p{L}_]/u,e.optional(/[\p{L}0-9_.-]*:/u),/[\p{L}0-9_.-]*/u),r=/[\p{L}0-9._:-]+/u,a={className:"symbol",begin:/&[a-z]+;|&#[0-9]+;|&#x[a-f0-9]+;/},s={begin:/\s/,contains:[{className:"keyword",begin:/#?[a-z_][a-z1-9_-]+/,illegal:/\n/}]},i=n.inherit(s,{begin:/\(/,end:/\)/}),o=n.inherit(n.APOS_STRING_MODE,{className:"string"}),c=n.inherit(n.QUOTE_STRING_MODE,{className:"string"}),u={endsWithParent:!0,illegal:/</,relevance:0,contains:[{className:"attr",begin:r,relevance:0},{begin:/=\s*/,relevance:0,contains:[{className:"string",endsParent:!0,variants:[{begin:/"/,end:/"/,contains:[a]},{begin:/'/,end:/'/,contains:[a]},{begin:/[^\s"'=<>`]+/}]}]}]};return{name:"HTML, XML",aliases:["html","xhtml","rss","atom","xjb","xsd","xsl","plist","wsf","svg"],case_insensitive:!0,unicodeRegex:!0,contains:[{className:"meta",begin:/<![a-z]/,end:/>/,relevance:10,contains:[s,c,o,i,{begin:/\[/,end:/\]/,contains:[{className:"meta",begin:/<![a-z]/,end:/>/,contains:[s,i,c,o]}]}]},n.COMMENT(/<!--/,/-->/,{relevance:10}),{begin:/<!\[CDATA\[/,end:/\]\]>/,relevance:10},a,{className:"meta",end:/\?>/,variants:[{begin:/<\?xml/,relevance:10,contains:[c]},{begin:/<\?[a-z][a-z0-9]+/}]},{className:"tag",begin:/<style(?=\s|>)/,end:/>/,keywords:{name:"style"},contains:[u],starts:{end:/<\/style>/,returnEnd:!0,subLanguage:"css"}},{className:"tag",begin:/<script(?=\s|>)/,end:/>/,keywords:{name:"script"},contains:[u],starts:{end:/<\/script>/,returnEnd:!0,subLanguage:"javascript"}},{className:"tag",begin:/<>|<\/>/},{className:"tag",begin:e.concat(/</,e.lookahead(e.concat(t,e.either(/\/>/,/>/,/\s/)))),end:/\/?>/,contains:[{className:"name",begin:t,relevance:0,starts:u}]},{className:"tag",begin:e.concat(/<\//,e.lookahead(e.concat(t,/>/))),contains:[{className:"name",begin:t,relevance:0},{begin:/>/,relevance:0,endsParent:!0}]}]}}function ci(n){let e="true false yes no null",t="[\\w#;/?:@&=+$,.~*'()[\\]]+",r={className:"attr",variants:[{begin:/[\w*@][\w*@ :()\./-]*:(?=[ \t]|$)/},{begin:/"[\w*@][\w*@ :()\./-]*":(?=[ \t]|$)/},{begin:/'[\w*@][\w*@ :()\./-]*':(?=[ \t]|$)/}]},a={className:"template-variable",variants:[{begin:/\{\{/,end:/\}\}/},{begin:/%\{/,end:/\}/}]},s={className:"string",relevance:0,begin:/'/,end:/'/,contains:[{match:/''/,scope:"char.escape",relevance:0}]},i={className:"string",relevance:0,variants:[{begin:/"/,end:/"/},{begin:/\S+/}],contains:[n.BACKSLASH_ESCAPE,a]},o=n.inherit(i,{variants:[{begin:/'/,end:/'/,contains:[{begin:/''/,relevance:0}]},{begin:/"/,end:/"/},{begin:/[^\s,{}[\]]+/}]}),m={className:"number",begin:"\\b"+"[0-9]{4}(-[0-9][0-9]){0,2}"+"([Tt \\t][0-9][0-9]?(:[0-9][0-9]){2})?"+"(\\.[0-9]*)?"+"([ \\t])*(Z|[-+][0-9][0-9]?(:[0-9][0-9])?)?"+"\\b"},_={end:",",endsWithParent:!0,excludeEnd:!0,keywords:e,relevance:0},p={begin:/\{/,end:/\}/,contains:[_],illegal:"\\n",relevance:0},g={begin:"\\[",end:"\\]",contains:[_],illegal:"\\n",relevance:0},S=[r,{className:"meta",begin:"^---\\s*$",relevance:10},{className:"string",begin:"[\\|>]([1-9]?[+-])?[ ]*\\n( +)[^ ][^\\n]*\\n(\\2[^\\n]+\\n?)*"},{begin:"<%[%=-]?",end:"[%-]?%>",subLanguage:"ruby",excludeBegin:!0,excludeEnd:!0,relevance:0},{className:"type",begin:"!\\w+!"+t},{className:"type",begin:"!<"+t+">"},{className:"type",begin:"!"+t},{className:"type",begin:"!!"+t},{className:"meta",begin:"&"+n.UNDERSCORE_IDENT_RE+"$"},{className:"meta",begin:"\\*"+n.UNDERSCORE_IDENT_RE+"$"},{className:"bullet",begin:"-(?=[ ]|$)",relevance:0},n.HASH_COMMENT_MODE,{beginKeywords:e,keywords:{literal:e}},m,{className:"number",begin:n.C_NUMBER_RE+"\\b",relevance:0},p,g,s,i],M=[...S];return M.pop(),M.push(o),_.contains=M,{name:"YAML",case_insensitive:!0,aliases:["yml"],contains:S}}var On=Object.freeze({"1c":"",abnf:"",accesslog:"",actionscript:"as",ada:"",angelscript:"asc",apache:"apacheconf",applescript:"osascript",arcade:"",arduino:"ino",armasm:"arm",asciidoc:"adoc",aspectj:"",autohotkey:"ahk",autoit:"",avrasm:"",awk:"",axapta:"x++",bash:"sh zsh",basic:"",bnf:"",brainfuck:"bf",c:"h",cal:"",capnproto:"capnp",ceylon:"",clean:"dcl icl",clojure:"clj edn","clojure-repl":"",cmake:"cmake.in",coffeescript:"coffee cson iced",coq:"",cos:"cls",cpp:"c++ cc cxx h++ hh hpp hxx",crmsh:"crm pcmk",crystal:"cr",csharp:"c# cs",csp:"",css:"",d:"",dart:"",delphi:"dfm dpr pas pascal",diff:"patch",django:"jinja",dns:"bind zone",dockerfile:"docker",dos:"bat batch cmd",dsconfig:"",dts:"",dust:"dst",ebnf:"",elixir:"ex exs",elm:"",erb:"",erlang:"erl","erlang-repl":"",excel:"xls xlsx",fix:"",flix:"",fortran:"f90 f95",freedesktop:"desktop systemd",fsharp:"f# fs",gams:"gms",gauss:"gss",gcode:"nc",gherkin:"feature",glsl:"",gml:"",go:"golang",golo:"",gradle:"",graphql:"gql",groovy:"",haml:"",handlebars:"hbs html.handlebars html.hbs htmlbars",haskell:"hs",haxe:"hx",hsp:"",http:"https",hy:"hylang",inform7:"i7",ini:"toml",irpf90:"",isbl:"",java:"jsp",javascript:"cjs js jsx mjs","jboss-cli":"wildfly-cli",json:"json5 jsonc",julia:"","julia-repl":"jldoctest",kotlin:"kt ktm kts ktx",lasso:"lassoscript ls",latex:"tex",ldif:"",leaf:"",less:"",lisp:"",livecodeserver:"",livescript:"ls",llvm:"",lsl:"",lua:"pluto",makefile:"mak make mk",markdown:"md mkd mkdown",mathematica:"mma wl",matlab:"",maxima:"",mel:"",mercury:"m moo",mipsasm:"mips",mizar:"",mojolicious:"",monkey:"",moonscript:"moon",n1ql:"",nestedtext:"nt",nginx:"nginxconf",nim:"",nix:"nixos","node-repl":"",nsis:"",objectivec:"mm obj-c obj-c++ objc objective-c++",ocaml:"ml",openscad:"scad",oxygene:"",parser3:"",perl:"pl pm",pf:"pf.conf",pgsql:"postgres postgresql",php:"","php-template":"",plaintext:"text txt",pony:"",powershell:"ps ps1 pwsh",processing:"pde",profile:"",prolog:"",properties:"",protobuf:"proto",puppet:"pp",purebasic:"pb pbi",python:"gyp ipython py","python-repl":"pycon",q:"k kdb",qml:"qt",r:"",reasonml:"re",rib:"",roboconf:"graph instances",routeros:"mikrotik",rsl:"",ruby:"gemspec irb podspec rb thor",ruleslanguage:"",rust:"rs",sas:"",scala:"",scheme:"scm",scilab:"sci",scss:"",shell:"console shellsession",smali:"",smalltalk:"st",sml:"ml",sqf:"",sql:"",stan:"stanfuncs",stata:"ado do",step21:"p21 step stp",stylus:"styl",subunit:"",swift:"",taggerscript:"",tap:"",tcl:"tk",thrift:"",tp:"",twig:"craftcms",typescript:"cts mts ts tsx",vala:"",vbnet:"vb",vbscript:"vbs","vbscript-html":"",verilog:"sv svh v",vhdl:"",vim:"",wasm:"",wren:"",x86asm:"",xl:"tao",xml:"atom html plist rss svg wsf xhtml xjb xsd xsl",xquery:"xpath xq xqm",yaml:"yml",zephir:"zep"});function Rc(n,e){this.v=n,this.k=e}function ui(n,e){(e==null||e>n.length)&&(e=n.length);for(var t=0,r=Array(e);t<e;t++)r[t]=n[t];return r}function Oc(n){if(Array.isArray(n))return n}function Ic(n,e){var t=n==null?null:typeof Symbol<"u"&&n[Symbol.iterator]||n["@@iterator"];if(t!=null){var r,a,s,i,o=[],c=!0,u=!1;try{if(s=(t=t.call(n)).next,e===0){if(Object(t)!==t)return;c=!1}else for(;!(c=(r=s.call(t)).done)&&(o.push(r.value),o.length!==e);c=!0);}catch(h){u=!0,a=h}finally{try{if(!c&&t.return!=null&&(i=t.return(),Object(i)!==i))return}finally{if(u)throw a}}return o}}function Dc(){throw new TypeError(`Invalid attempt to destructure non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`)}function Pc(n,e){return Oc(n)||Ic(n,e)||zc(n,e)||Dc()}function zc(n,e){if(n){if(typeof n=="string")return ui(n,e);var t={}.toString.call(n).slice(8,-1);return t==="Object"&&n.constructor&&(t=n.constructor.name),t==="Map"||t==="Set"?Array.from(n):t==="Arguments"||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t)?ui(n,e):void 0}}function In(n){var e,t;function r(s,i){try{var o=n[s](i),c=o.value,u=c instanceof Rc;Promise.resolve(u?c.v:c).then(function(h){if(u){var b=s==="return"&&c.k?s:"next";if(!c.k||h.done)return r(b,h);h=n[b](h).value}a(!!o.done,h)},function(h){r("throw",h)})}catch(h){a(2,h)}}function a(s,i){s===2?e.reject(i):e.resolve({value:i,done:s}),(e=e.next)?r(e.key,e.arg):t=null}this._invoke=function(s,i){return new Promise(function(o,c){var u={key:s,arg:i,resolve:o,reject:c,next:null};t?t=t.next=u:(e=t=u,r(s,i))})},typeof n.return!="function"&&(this.return=void 0)}In.prototype[typeof Symbol=="function"&&Symbol.asyncIterator||"@@asyncIterator"]=function(){return this},In.prototype.next=function(n){return this._invoke("next",n)},In.prototype.throw=function(n){return this._invoke("throw",n)},In.prototype.return=function(n){return this._invoke("return",n)};var Si=Object.entries,di=Object.setPrototypeOf,Bc=Object.isFrozen,Ti=Object.getPrototypeOf,ki=Object.getOwnPropertyDescriptor,he=Object.freeze,fe=Object.seal,Ut=Object.create,Ni=typeof Reflect<"u"&&Reflect,Gr=Ni.apply,Vr=Ni.construct;he||(he=function(e){return e});fe||(fe=function(e){return e});Gr||(Gr=function(e,t){for(var r=arguments.length,a=new Array(r>2?r-2:0),s=2;s<r;s++)a[s-2]=arguments[s];return e.apply(t,a)});Vr||(Vr=function(e){for(var t=arguments.length,r=new Array(t>1?t-1:0),a=1;a<t;a++)r[a-1]=arguments[a];return new e(...r)});var Ke=re(Array.prototype.forEach);Array.prototype.indexOf;var Uc=re(Array.prototype.lastIndexOf),hi=re(Array.prototype.pop),tn=re(Array.prototype.push),jc=re(Array.prototype.slice),Fc=re(Array.prototype.splice),jt=Array.isArray,Dr=Ci(Set),Pr=re(Set.prototype.add),nn=re(Set.prototype.has),gt=re(String.prototype.toLowerCase),zr=re(String.prototype.toString),pi=re(String.prototype.match),rn=re(String.prototype.replace),fi=re(String.prototype.indexOf),$c=re(String.prototype.trim),Hc=re(Number.prototype.toString),Gc=re(Boolean.prototype.toString),mi=typeof BigInt>"u"?null:re(BigInt.prototype.toString),gi=typeof Symbol>"u"?null:re(Symbol.prototype.toString),we=re(Object.prototype.hasOwnProperty),an=re(Object.prototype.toString),pe=re(RegExp.prototype.test),We=Ci(TypeError);function re(n){return function(e){e instanceof RegExp&&(e.lastIndex=0);for(var t=arguments.length,r=new Array(t>1?t-1:0),a=1;a<t;a++)r[a-1]=arguments[a];return Gr(n,e,r)}}function Ci(n){return function(){for(var e=arguments.length,t=new Array(e),r=0;r<e;r++)t[r]=arguments[r];return Vr(n,t)}}function G(n,e){let t=arguments.length>2&&arguments[2]!==void 0?arguments[2]:gt;if(di&&di(n,null),!jt(e))return n;let r=e.length;for(;r--;){let a=e[r];if(typeof a=="string"){let s=t(a);s!==a&&(Bc(e)||(e[r]=s),a=s)}n[a]=!0}return n}function Vc(n){for(let e=0;e<n.length;e++)we(n,e)||(n[e]=null);return n}function Te(n){let e=Ut(null);for(let r of Si(n)){var t=Pc(r,2);let a=t[0],s=t[1];we(n,a)&&(jt(s)?e[a]=Vc(s):s&&typeof s=="object"&&s.constructor===Object?e[a]=Te(s):e[a]=s)}return e}function qc(n){switch(typeof n){case"string":return n;case"number":return Hc(n);case"boolean":return Gc(n);case"bigint":return mi?mi(n):"0";case"symbol":return gi?gi(n):"Symbol()";case"undefined":return an(n);case"function":case"object":{if(n===null)return an(n);let e=n,t=Ce(e,"toString");if(typeof t=="function"){let r=t(e);return typeof r=="string"?r:an(r)}return an(n)}default:return an(n)}}function Ce(n,e){for(;n!==null;){let r=ki(n,e);if(r){if(r.get)return re(r.get);if(typeof r.value=="function")return re(r.value)}n=Ti(n)}function t(){return null}return t}function Kc(n,e){for(;n!==null;){let t=ki(n,e);if(t)return t.get?re(t.get):null;n=Ti(n)}return null}function Wc(n){try{return pe(n,""),!0}catch{return!1}}var bi=he(["a","abbr","acronym","address","area","article","aside","audio","b","bdi","bdo","big","blink","blockquote","body","br","button","canvas","caption","center","cite","code","col","colgroup","content","data","datalist","dd","decorator","del","details","dfn","dialog","dir","div","dl","dt","element","em","fieldset","figcaption","figure","font","footer","form","h1","h2","h3","h4","h5","h6","head","header","hgroup","hr","html","i","img","input","ins","kbd","label","legend","li","main","map","mark","marquee","menu","menuitem","meter","nav","nobr","ol","optgroup","option","output","p","picture","pre","progress","q","rp","rt","ruby","s","samp","search","section","select","shadow","slot","small","source","spacer","span","strike","strong","style","sub","summary","sup","table","tbody","td","template","textarea","tfoot","th","thead","time","tr","track","tt","u","ul","var","video","wbr"]),Br=he(["svg","a","altglyph","altglyphdef","altglyphitem","animatecolor","animatemotion","animatetransform","circle","clippath","defs","desc","ellipse","enterkeyhint","exportparts","filter","font","g","glyph","glyphref","hkern","image","inputmode","line","lineargradient","marker","mask","metadata","mpath","part","path","pattern","polygon","polyline","radialgradient","rect","stop","style","switch","symbol","text","textpath","title","tref","tspan","view","vkern"]),Ur=he(["feBlend","feColorMatrix","feComponentTransfer","feComposite","feConvolveMatrix","feDiffuseLighting","feDisplacementMap","feDistantLight","feDropShadow","feFlood","feFuncA","feFuncB","feFuncG","feFuncR","feGaussianBlur","feImage","feMerge","feMergeNode","feMorphology","feOffset","fePointLight","feSpecularLighting","feSpotLight","feTile","feTurbulence"]),Yc=he(["animate","color-profile","cursor","discard","font-face","font-face-format","font-face-name","font-face-src","font-face-uri","foreignobject","hatch","hatchpath","mesh","meshgradient","meshpatch","meshrow","missing-glyph","script","set","solidcolor","unknown","use"]),jr=he(["math","menclose","merror","mfenced","mfrac","mglyph","mi","mlabeledtr","mmultiscripts","mn","mo","mover","mpadded","mphantom","mroot","mrow","ms","mspace","msqrt","mstyle","msub","msup","msubsup","mtable","mtd","mtext","mtr","munder","munderover","mprescripts"]),Zc=he(["maction","maligngroup","malignmark","mlongdiv","mscarries","mscarry","msgroup","mstack","msline","msrow","semantics","annotation","annotation-xml","mprescripts","none"]),yi=he(["#text"]),vi=he(["accept","action","align","alt","autocapitalize","autocomplete","autopictureinpicture","autoplay","background","bgcolor","border","capture","cellpadding","cellspacing","checked","cite","class","clear","color","cols","colspan","command","commandfor","controls","controlslist","coords","crossorigin","datetime","decoding","default","dir","disabled","disablepictureinpicture","disableremoteplayback","download","draggable","enctype","enterkeyhint","exportparts","face","for","headers","height","hidden","high","href","hreflang","id","inert","inputmode","integrity","ismap","kind","label","lang","list","loading","loop","low","max","maxlength","media","method","min","minlength","multiple","muted","name","nonce","noshade","novalidate","nowrap","open","optimum","part","pattern","placeholder","playsinline","popover","popovertarget","popovertargetaction","poster","preload","pubdate","radiogroup","readonly","rel","required","rev","reversed","role","rows","rowspan","spellcheck","scope","selected","shape","size","sizes","slot","span","srclang","start","src","srcset","step","style","summary","tabindex","title","translate","type","usemap","valign","value","width","wrap","xmlns"]),Fr=he(["accent-height","accumulate","additive","alignment-baseline","amplitude","ascent","attributename","attributetype","azimuth","basefrequency","baseline-shift","begin","bias","by","class","clip","clippathunits","clip-path","clip-rule","color","color-interpolation","color-interpolation-filters","color-profile","color-rendering","cx","cy","d","dx","dy","diffuseconstant","direction","display","divisor","dominant-baseline","dur","edgemode","elevation","end","exponent","fill","fill-opacity","fill-rule","filter","filterunits","flood-color","flood-opacity","font-family","font-size","font-size-adjust","font-stretch","font-style","font-variant","font-weight","fx","fy","g1","g2","glyph-name","glyphref","gradientunits","gradienttransform","height","href","id","image-rendering","in","in2","intercept","k","k1","k2","k3","k4","kerning","keypoints","keysplines","keytimes","lang","lengthadjust","letter-spacing","kernelmatrix","kernelunitlength","lighting-color","local","marker-end","marker-mid","marker-start","markerheight","markerunits","markerwidth","maskcontentunits","maskunits","max","mask","mask-type","media","method","mode","min","name","numoctaves","offset","operator","opacity","order","orient","orientation","origin","overflow","paint-order","path","pathlength","patterncontentunits","patterntransform","patternunits","pointer-events","points","preservealpha","preserveaspectratio","primitiveunits","r","rx","ry","radius","refx","refy","repeatcount","repeatdur","restart","result","rotate","scale","seed","shape-rendering","slope","specularconstant","specularexponent","spreadmethod","startoffset","stddeviation","stitchtiles","stop-color","stop-opacity","stroke-dasharray","stroke-dashoffset","stroke-linecap","stroke-linejoin","stroke-miterlimit","stroke-opacity","stroke","stroke-width","style","surfacescale","systemlanguage","tabindex","tablevalues","targetx","targety","transform","transform-origin","text-anchor","text-decoration","text-orientation","text-rendering","textlength","type","u1","u2","unicode","values","vector-effect","viewbox","visibility","version","vert-adv-y","vert-origin-x","vert-origin-y","width","word-spacing","wrap","writing-mode","xchannelselector","ychannelselector","x","x1","x2","xmlns","y","y1","y2","z","zoomandpan"]),xi=he(["accent","accentunder","align","bevelled","close","columnalign","columnlines","columnspacing","columnspan","denomalign","depth","dir","display","displaystyle","encoding","fence","frame","height","href","id","largeop","length","linethickness","lquote","lspace","mathbackground","mathcolor","mathsize","mathvariant","maxsize","minsize","movablelimits","notation","numalign","open","rowalign","rowlines","rowspacing","rowspan","rspace","rquote","scriptlevel","scriptminsize","scriptsizemultiplier","selection","separator","separators","stretchy","subscriptshift","supscriptshift","symmetric","voffset","width","xmlns"]),Dn=he(["xlink:href","xml:id","xlink:title","xml:space","xmlns:xlink"]),Jc=fe(/{{[\w\W]*|^[\w\W]*}}/g),Xc=fe(/<%[\w\W]*|^[\w\W]*%>/g),Qc=fe(/\${[\w\W]*/g),eu=fe(/^data-[\-\w.\u00B7-\uFFFF]+$/),tu=fe(/^aria-[\-\w]+$/),_i=fe(/^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i),nu=fe(/^(?:\w+script|data):/i),ru=fe(/[\u0000-\u0020\u00A0\u1680\u180E\u2000-\u2029\u205F\u3000]/g),au=fe(/^html$/i),su=fe(/^[a-z][.\w]*(-[.\w]+)+$/i),$r=fe(/<[/\w!]/g),wi=fe(/<[/\w]/g),iu=fe(/<\/no(script|embed|frames)/i),Ei=fe(/\/>/i),le={element:1,attribute:2,text:3,cdataSection:4,entityReference:5,entityNode:6,processingInstruction:7,comment:8,document:9,documentType:10,documentFragment:11,notation:12},ou=he(G({},["style","script","xmp","iframe","noembed","noframes","plaintext","noscript"])),lu=function(){return typeof window>"u"?null:window},cu=function(e,t){if(typeof e!="object"||typeof e.createPolicy!="function")return null;let r=null,a="data-tt-policy-suffix";t&&t.hasAttribute(a)&&(r=t.getAttribute(a));let s="dompurify"+(r?"#"+r:"");try{return e.createPolicy(s,{createHTML(i){return i},createScriptURL(i){return i}})}catch{return console.warn("TrustedTypes policy "+s+" could not be created."),null}},Ai=function(){return{afterSanitizeAttributes:[],afterSanitizeElements:[],afterSanitizeShadowDOM:[],beforeSanitizeAttributes:[],beforeSanitizeElements:[],beforeSanitizeShadowDOM:[],uponSanitizeAttribute:[],uponSanitizeElement:[],uponSanitizeShadowNode:[]}},rt=function(e,t,r,a){return we(e,t)&&jt(e[t])?G(a.base?Te(a.base):{},e[t],a.transform):r},Hr=function(e,t,r){let a=we(e,t)?e[t]:void 0;return a&&typeof a=="object"?Te(a):r()};function Mi(){let n=arguments.length>0&&arguments[0]!==void 0?arguments[0]:lu(),e=x=>Mi(x);if(e.version="3.4.17",e.removed=[],!n||!n.document||n.document.nodeType!==le.document||!n.Element)return e.isSupported=!1,e;let t=n.document,r=t,a=r.currentScript;n.DocumentFragment;let s=n.HTMLTemplateElement,i=n.Node,o=n.Element,c=n.NodeFilter;n.NamedNodeMap===void 0&&(n.NamedNodeMap||n.MozNamedAttrMap),n.HTMLFormElement;let u=n.DOMParser,h=n.trustedTypes,b=o.prototype,m=Ce(b,"cloneNode"),_=Ce(b,"remove"),p=Ce(b,"removeAttributeNode"),g=Ce(b,"nextSibling"),S=Ce(b,"childNodes"),M=Ce(b,"parentNode"),D=Ce(b,"shadowRoot"),j=Ce(b,"attributes"),P=i&&i.prototype?Ce(i.prototype,"nodeType"):null,q=i&&i.prototype?Ce(i.prototype,"nodeName"):null,X=i&&i.prototype?Ce(i.prototype,"ownerDocument"):null,ae=function(l){return P?P(l):l.nodeType},ie=function(l){return q?q(l):l.nodeName},Le=Kc(b,"namespaceURI"),ke=function(l){return Le?Le(l):l.namespaceURI};if(typeof s=="function"){let x=t.createElement("template");x.content&&x.content.ownerDocument&&(t=x.content.ownerDocument)}let se,ye="",Be,Ne=!1,Re=0,w=function(){if(Re>0)throw We('A configured TRUSTED_TYPES_POLICY callback (createHTML or createScriptURL) must not call DOMPurify.sanitize, as that causes infinite recursion. Do not pass a policy whose callbacks wrap DOMPurify as TRUSTED_TYPES_POLICY; see the "DOMPurify and Trusted Types" section of the README.')},k=function(l){w(),Re++;try{return se.createHTML(l)}finally{Re--}},R=function(l){w(),Re++;try{return se.createScriptURL(l)}finally{Re--}},F=function(){return Ne||(Be=cu(h,a),Ne=!0),Be},E=t,L=E.implementation,z=E.createNodeIterator,Y=E.createDocumentFragment,B=E.getElementsByTagName,Q=r.importNode,K=Ai();e.isSupported=typeof Si=="function"&&typeof M=="function"&&L&&L.createHTMLDocument!==void 0;let dn=Jc,hn=Xc,Kn=Qc,Wn=eu,Yn=tu,Zn=nu,st=ru,pn=su,Ae=_i,J=null,it=G({},[...bi,...Br,...Ur,...jr,...yi]),T=null,_t=G({},[...vi,...Fr,...xi,...Dn]),Z=Object.seal(Ut(null,{tagNameCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},attributeNameCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},allowCustomizedBuiltInElements:{writable:!0,configurable:!1,enumerable:!0,value:!1}})),V=null,ot=null,me=Object.seal(Ut(null,{tagCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},attributeCheck:{writable:!0,configurable:!1,enumerable:!0,value:null}})),wt=!0,lt=!0,A=!1,N=!0,O=!1,$=!0,ee=!1,Se=!1,Et=null,At=null,Jn=!1,St=!1,fn=!1,mn=!1,ua=!0,da=!1,ha="user-content-",Xn=!0,Qn=!1,ct=null,Tt={},ut=null,pa=G({},["annotation-xml","audio","colgroup","desc","foreignobject","head","iframe","math","mi","mn","mo","ms","mtext","noembed","noframes","noscript","plaintext","script","selectedcontent","style","svg","template","thead","title","video","xmp"]),fa=null,ma=G({},["audio","video","img","source","image","track"]),ga=null,ba=G({},["alt","class","for","id","label","name","pattern","placeholder","role","summary","title","value","style","xmlns"]),gn="http://www.w3.org/1998/Math/MathML",bn="http://www.w3.org/2000/svg",Ue="http://www.w3.org/1999/xhtml",kt=Ue,er=!1,tr=null,Eo=G({},[gn,bn,Ue],zr),ya=he(["mi","mo","mn","ms","mtext"]),nr=G({},ya),va=he(["annotation-xml"]),rr=G({},va),Ao=G({},["title","style","font","a","script"]),Gt=null,So=["application/xhtml+xml","text/html"],To="text/html",oe=null,Nt=null,ko=t.createElement("form"),xa=function(l){return l instanceof RegExp||l instanceof Function},ar=function(){let l=arguments.length>0&&arguments[0]!==void 0?arguments[0]:{};if(Nt&&Nt===l)return;(!l||typeof l!="object")&&(l={}),l=Te(l),Gt=So.indexOf(l.PARSER_MEDIA_TYPE)===-1?To:l.PARSER_MEDIA_TYPE,oe=Gt==="application/xhtml+xml"?zr:gt,J=rt(l,"ALLOWED_TAGS",it,{transform:oe}),T=rt(l,"ALLOWED_ATTR",_t,{transform:oe}),tr=rt(l,"ALLOWED_NAMESPACES",Eo,{transform:zr}),ga=rt(l,"ADD_URI_SAFE_ATTR",ba,{transform:oe,base:ba}),fa=rt(l,"ADD_DATA_URI_TAGS",ma,{transform:oe,base:ma}),ut=rt(l,"FORBID_CONTENTS",pa,{transform:oe}),V=rt(l,"FORBID_TAGS",Te({}),{transform:oe}),ot=rt(l,"FORBID_ATTR",Te({}),{transform:oe}),Tt=we(l,"USE_PROFILES")?l.USE_PROFILES&&typeof l.USE_PROFILES=="object"?Te(l.USE_PROFILES):l.USE_PROFILES:!1,wt=l.ALLOW_ARIA_ATTR!==!1,lt=l.ALLOW_DATA_ATTR!==!1,A=l.ALLOW_UNKNOWN_PROTOCOLS||!1,N=l.ALLOW_SELF_CLOSE_IN_ATTR!==!1,O=l.SAFE_FOR_TEMPLATES||!1,$=l.SAFE_FOR_XML!==!1,ee=l.WHOLE_DOCUMENT||!1,St=l.RETURN_DOM||!1,fn=l.RETURN_DOM_FRAGMENT||!1,mn=l.RETURN_TRUSTED_TYPE||!1,Jn=l.FORCE_BODY||!1,ua=l.SANITIZE_DOM!==!1,da=l.SANITIZE_NAMED_PROPS||!1,Xn=l.KEEP_CONTENT!==!1,Qn=l.IN_PLACE||!1,Ae=Wc(l.ALLOWED_URI_REGEXP)?l.ALLOWED_URI_REGEXP:_i,kt=typeof l.NAMESPACE=="string"?l.NAMESPACE:Ue,nr=Hr(l,"MATHML_TEXT_INTEGRATION_POINTS",()=>G({},ya)),rr=Hr(l,"HTML_INTEGRATION_POINTS",()=>G({},va));let d=Hr(l,"CUSTOM_ELEMENT_HANDLING",()=>Ut(null));if(Z=Ut(null),we(d,"tagNameCheck")&&xa(d.tagNameCheck)&&(Z.tagNameCheck=d.tagNameCheck),we(d,"attributeNameCheck")&&xa(d.attributeNameCheck)&&(Z.attributeNameCheck=d.attributeNameCheck),we(d,"allowCustomizedBuiltInElements")&&typeof d.allowCustomizedBuiltInElements=="boolean"&&(Z.allowCustomizedBuiltInElements=d.allowCustomizedBuiltInElements),fe(Z),O&&(lt=!1),fn&&(St=!0),Tt&&(J=G({},yi),T=Ut(null),Tt.html===!0&&(G(J,bi),G(T,vi)),Tt.svg===!0&&(G(J,Br),G(T,Fr),G(T,Dn)),Tt.svgFilters===!0&&(G(J,Ur),G(T,Fr),G(T,Dn)),Tt.mathMl===!0&&(G(J,jr),G(T,xi),G(T,Dn))),me.tagCheck=null,me.attributeCheck=null,we(l,"ADD_TAGS")&&(typeof l.ADD_TAGS=="function"?me.tagCheck=l.ADD_TAGS:jt(l.ADD_TAGS)&&(J===it&&(J=Te(J)),G(J,l.ADD_TAGS,oe))),we(l,"ADD_ATTR")&&(typeof l.ADD_ATTR=="function"?me.attributeCheck=l.ADD_ATTR:jt(l.ADD_ATTR)&&(T===_t&&(T=Te(T)),G(T,l.ADD_ATTR,oe))),we(l,"ADD_FORBID_CONTENTS")&&jt(l.ADD_FORBID_CONTENTS)&&(ut===pa&&(ut=Te(ut)),G(ut,l.ADD_FORBID_CONTENTS,oe)),Xn&&(J["#text"]=!0),ee&&G(J,["html","head","body"]),J.table&&(G(J,["tbody"]),delete V.tbody),l.TRUSTED_TYPES_POLICY){if(typeof l.TRUSTED_TYPES_POLICY.createHTML!="function")throw We('TRUSTED_TYPES_POLICY configuration option must provide a "createHTML" hook.');if(typeof l.TRUSTED_TYPES_POLICY.createScriptURL!="function")throw We('TRUSTED_TYPES_POLICY configuration option must provide a "createScriptURL" hook.');let y=se;se=l.TRUSTED_TYPES_POLICY;try{ye=k("")}catch(v){throw se=y,v}}else l.TRUSTED_TYPES_POLICY===null?(se=void 0,ye=""):(se===void 0&&(se=F()),se&&typeof ye=="string"&&(ye=k("")));he&&he(l),Nt=l},_a=G({},[...Br,...Ur,...Yc]),wa=G({},[...jr,...Zc]),No=function(l,d,y){return d.namespaceURI===Ue?l==="svg":d.namespaceURI===gn?l==="svg"&&(y==="annotation-xml"||nr[y]):!!_a[l]},Co=function(l,d,y){return d.namespaceURI===Ue?l==="math":d.namespaceURI===bn?l==="math"&&rr[y]:!!wa[l]},Mo=function(l,d,y){return d.namespaceURI===bn&&!rr[y]||d.namespaceURI===gn&&!nr[y]?!1:!wa[l]&&(Ao[l]||!_a[l])},Lo=function(l){let d=ke(l),y=gt(ie(l)),v=M(l),C,I;return v&&ae(v)===le.element?(C={namespaceURI:ke(v)},I=gt(ie(v))):(C={namespaceURI:kt},I="template"),tr[d]?d===bn?No(y,C,I):d===gn?Co(y,C,I):d===Ue?Mo(y,C,I):!!(Gt==="application/xhtml+xml"&&tr[d]):!1},Qe=function(l){tn(e.removed,{element:l});try{M(l).removeChild(l)}catch{if(_(l),!M(l))throw We("a node selected for removal could not be detached from its tree and cannot be safely returned; refusing to sanitize in place")}},Ea=function(l,d,y){try{p(l,d)}catch{try{l.removeAttribute(y)}catch{}}},sr=function(l){or(l);let d=S(l);d&&Ke(jc(d),v=>{try{_(v)}catch{}});let y=ae(l)===le.element?j(l):null;if(y)for(let v=y.length-1;v>=0;--v){let C=y[v],I=C&&C.name;typeof I=="string"&&Ea(l,C,I)}},Ct=function(l,d,y){if(!y)try{y=d.getAttributeNode(l)}catch{y=null}tn(e.removed,{attribute:y||null,from:d});try{y?p(d,y):d.removeAttribute(l)}catch{try{d.removeAttribute(l)}catch{}}if(l==="is")if(St||fn)try{Qe(d)}catch{}else try{d.setAttribute(l,"")}catch{}},Aa=function(l){let d=j(l);if(d)for(let y=d.length-1;y>=0;--y){let v=d[y],C=v&&v.name;typeof C!="string"||T[oe(C)]||Ea(l,v,C)}},ir=function(l,d){let y=arguments.length>2&&arguments[2]!==void 0?arguments[2]:!1,v=[l];for(;v.length>0;){let C=v.pop();if(d(C)===!1)continue;if(y&&ae(C)===le.element){let U=D(C);et(U)&&v.push(U)}let I=S(C);if(I)for(let U=I.length-1;U>=0;--U)v.push(I[U])}},or=function(l){ir(l,d=>{ae(d)===le.element&&Aa(d)})},lr=function(l){let d=[];return ir(l,y=>{d.push(y)},!0),d},Ro=function(l,d){let y=Dr();Ke(lr(l),v=>{ae(v)===le.element&&Pr(y,v)}),Ke(d,v=>{ae(v)===le.element&&!nn(y,v)&&Aa(v)})},Sa=function(l,d){let y=!1;return Ke(e.removed,v=>{v.element&&(y=y||v.element===l,or(v.element))}),Ro(l,d),y},Oo=8,Io=function(l,d){let y=ct,v=null,C=()=>(v||(v=Dr(),Ke(d,I=>{Pr(v,I)})),v);for(let I=0;;I++){let U=lr(l),ce=[l],je=!1;if(Ke(U,be=>{ae(be)===le.documentFragment?tn(ce,be):!je&&!nn(y,be)&&(je=nn(C(),be))}),!je)return;if(I>=Oo)throw We("the tree kept changing during in-place sanitization; refusing to return it");Ke(ce,(be,ve)=>{Do(be,ve>0,l,C())})}},Do=function(l,d,y,v){let C=cr(l),I;for(;I=C.nextNode();)!nn(v,I)||nn(ct,I)||(d&&Oe(K.uponSanitizeShadowNode,I,null),dr(I,y),hr(I,y),et(I.content)&&qt(I.content))},Po=function(l){ct&&Pr(ct,l)},Ta=function(l,d){return $?l==="patchsrc"?!0:l==="for"&&d!=="label"&&d!=="output":!1},zo=function(l){$&&ir(l,d=>{let y=ae(d);if(y===le.processingInstruction||y===le.comment&&pe(wi,d.data)){try{_(d)}catch{}return!1}if(y===le.element){let v=d,C=oe(ie(d));try{v.hasAttribute&&v.hasAttribute("patchsrc")&&v.removeAttribute("patchsrc"),v.hasAttribute&&v.hasAttribute("for")&&Ta("for",C)&&v.removeAttribute("for")}catch{}}return!0})},ka=function(l){let d=null,y=null;if(Jn)l="<remove></remove>"+l;else{let I=pi(l,/^[\r\n\t ]+/);y=I&&I[0]}Gt==="application/xhtml+xml"&&kt===Ue&&(l='<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body>'+l+"</body></html>");let v=se?k(l):l;if(kt===Ue)try{d=new u().parseFromString(v,Gt)}catch{}if(!d||!d.documentElement){d=L.createDocument(kt,"template",null);try{d.documentElement.innerHTML=er?ye:v}catch{}}let C=d.body||d.documentElement;return l&&y&&C.insertBefore(t.createTextNode(y),C.childNodes[0]||null),kt===Ue?B.call(d,ee?"html":"body")[0]:ee?d.documentElement:C},cr=function(l){let d=X?X(l):l.ownerDocument;return z.call(d||l,l,c.SHOW_ELEMENT|c.SHOW_COMMENT|c.SHOW_TEXT|c.SHOW_PROCESSING_INSTRUCTION|c.SHOW_CDATA_SECTION,null)},yn=function(l){return l=rn(l,dn," "),l=rn(l,hn," "),l=rn(l,Kn," "),l},ur=function(l){var d;Na(l);let y=(d=l.querySelectorAll)===null||d===void 0?void 0:d.call(l,"template");y&&Ke(y,v=>{et(v.content)&&ur(v.content)})},Na=function(l){l.normalize();let d=X?X(l):l.ownerDocument,y=z.call(d||l,l,c.SHOW_TEXT|c.SHOW_COMMENT|c.SHOW_CDATA_SECTION|c.SHOW_PROCESSING_INSTRUCTION,null),v=y.nextNode();for(;v;)v.data=yn(v.data),v=y.nextNode()},vn=function(l){let d=q?q(l):null;return typeof d!="string"||oe(d)!=="form"?!1:typeof l.nodeName!="string"||typeof l.textContent!="string"||typeof l.removeChild!="function"||l.attributes!==j(l)||typeof l.removeAttribute!="function"||typeof l.removeAttributeNode!="function"||typeof l.getAttributeNode!="function"||typeof l.setAttribute!="function"||typeof l.namespaceURI!="string"||typeof l.insertBefore!="function"||typeof l.hasChildNodes!="function"||l.nodeType!==P(l)||l.childNodes!==S(l)},et=function(l){if(!P||typeof l!="object"||l===null)return!1;try{return P(l)===le.documentFragment}catch{return!1}},Vt=function(l){if(!P||typeof l!="object"||l===null)return!1;try{return typeof P(l)=="number"}catch{return!1}};function Oe(x,l,d){x.length!==0&&Ke(x,y=>{y.call(e,l,d,Nt)})}let Bo=function(l,d){return!!($&&l.hasChildNodes()&&!Vt(l.firstElementChild)&&pe($r,l.textContent)&&pe($r,l.innerHTML)||$&&ou[d]&&ae(l)===le.element&&ke(l)===Ue&&(Vt(l.firstElementChild)||typeof l.textContent=="string"&&pe($r,l.textContent))||l.nodeType===le.processingInstruction||$&&l.nodeType===le.comment&&pe(wi,l.data))},xn=function(l,d){if(l instanceof RegExp)return pe(l,d);if(l instanceof Function){for(var y=arguments.length,v=new Array(y>2?y-2:0),C=2;C<y;C++)v[C-2]=arguments[C];return!!l(d,...v)}return!1},Uo=function(l,d,y){if(!V[d]&&La(d)&&xn(Z.tagNameCheck,d))return!1;if(Xn&&!ut[d]&&!ut[gt(d)]){let v=M(l),C=S(l);if(C&&v){let I=C.length;for(let U=I-1;U>=0;--U){let ce=l===y?m(C[U],!0):C[U];v.insertBefore(ce,g(l))}}}return Qe(l),!0},Ca=function(l,d,y,v){return l.length===0?d:d===y||d===v?Te(d):d},Mt=function(l,d){return l===d||M(l)!==null?!1:(Qn&&or(l),!0)},dr=function(l,d){if(Po(l),Oe(K.beforeSanitizeElements,l,null),Mt(l,d))return!0;if(vn(l))return Qe(l),!0;let y=oe(ie(l));if(J=Ca(K.uponSanitizeElement,J,it,Et),Oe(K.uponSanitizeElement,l,{tagName:y,allowedTags:J}),Mt(l,d))return!0;if(Bo(l,y))return Qe(l),!0;if(V[y]||!(me.tagCheck instanceof Function&&me.tagCheck(y))&&!J[y]){let v=Uo(l,y,d);return v===!1&&(Oe(K.afterSanitizeElements,l,null),Mt(l,d))?!0:v}if(ae(l)===le.element&&!Lo(l)||(y==="noscript"||y==="noembed"||y==="noframes")&&pe(iu,l.innerHTML))return Qe(l),!0;if(O&&l.nodeType===le.text){let v=yn(l.textContent);l.textContent!==v&&(tn(e.removed,{element:l.cloneNode()}),l.textContent=v)}return Oe(K.afterSanitizeElements,l,null),Mt(l,d)},Ma=function(l,d,y){if(ot[d]||Ta(d,l)||ua&&(d==="id"||d==="name")&&(y in t||y in ko))return!1;let v=T[d]||me.attributeCheck instanceof Function&&me.attributeCheck(d,l);return lt&&pe(Wn,d)||wt&&pe(Yn,d)?!0:v?ga[d]||pe(Ae,rn(y,st,""))||(d==="src"||d==="xlink:href"||d==="href")&&l!=="script"&&fi(y,"data:")===0&&fa[l]||A&&!pe(Zn,rn(y,st,""))?!0:!y:La(l)&&xn(Z.tagNameCheck,l)&&xn(Z.attributeNameCheck,d,l)||d==="is"&&Z.allowCustomizedBuiltInElements&&xn(Z.tagNameCheck,y)},jo=G({},["annotation-xml","color-profile","font-face","font-face-format","font-face-name","font-face-src","font-face-uri","missing-glyph"]),La=function(l){return!jo[gt(l)]&&pe(pn,l)},Fo=function(l,d,y,v){if(se&&typeof h=="object"&&typeof h.getAttributeType=="function"&&!y)switch(h.getAttributeType(l,d)){case"TrustedHTML":return k(v);case"TrustedScriptURL":return R(v)}return v},$o=function(l,d,y,v){try{return y?l.setAttributeNS(y,d,v):l.setAttribute(d,v),vn(l)?(Qe(l),!1):!0}catch{return Ct(d,l),!1}},Ra=function(l,d){return $&&pe(/((--!?|])>)|<\/(style|script|title|xmp|textarea|noscript|iframe|noembed|noframes)/i,d)?!0:gt(l)==="attributename"&&pi(d,"href")!==null},hr=function(l,d){if(Oe(K.beforeSanitizeAttributes,l,null),Mt(l,d))return;let y=l.attributes;if(!y||vn(l))return;T=Ca(K.uponSanitizeAttribute,T,_t,At);let v={attrName:"",attrValue:"",keepAttr:!0,allowedAttributes:T,forceKeepAttr:void 0},C=y.length,I=oe(l.nodeName);for(;C--;){let U=y[C],ce=U.name,je=U.namespaceURI,be=U.value,ve=oe(ce),Lt=be,xe=ce==="value"?Lt:$c(Lt),Oa=!1;if(v.attrName=ve,v.attrValue=xe,v.keepAttr=!0,v.forceKeepAttr=void 0,Oe(K.uponSanitizeAttribute,l,v),xe=v.attrValue,da&&(ve==="id"||ve==="name")&&fi(xe,ha)!==0&&(Ct(ce,l,U),xe=ha+xe,Oa=!0),Ra(ce,xe)){Ct(ce,l,U);continue}if(!v.forceKeepAttr){if(!v.keepAttr){Ct(ce,l,U);continue}if(!N&&pe(Ei,xe)){Ct(ce,l,U);continue}if(O&&(xe=yn(xe)),!Ma(I,ve,xe)){Ct(ce,l,U);continue}xe=Fo(I,ve,je,xe),xe!==Lt&&$o(l,ce,je,xe)&&Oa&&hi(e.removed)}}Oe(K.afterSanitizeAttributes,l,null),Mt(l,d)},qt=function(l){let d=null,y=cr(l);for(Oe(K.beforeSanitizeShadowDOM,l,null);d=y.nextNode();)if(Oe(K.uponSanitizeShadowNode,d,null),dr(d,l),hr(d,l),et(d.content)&&qt(d.content),ae(d)===le.element){let v=D(d);et(v)&&(pr(v),qt(v))}O&&Na(l),Oe(K.afterSanitizeShadowDOM,l,null)},pr=function(l){let d=[{node:l,shadow:null}];for(;d.length>0;){let y=d.pop();if(y.shadow){qt(y.shadow);continue}let v=y.node,C=ae(v)===le.element,I=S(v);if(I)for(let U=I.length-1;U>=0;--U)d.push({node:I[U],shadow:null});if(C){let U=q?q(v):null;if(typeof U=="string"&&oe(U)==="template"){let ce=v.content;et(ce)&&d.push({node:ce,shadow:null})}}if(C){let U=D(v);et(U)&&d.push({node:null,shadow:U},{node:U,shadow:null})}}};return e.sanitize=function(x){let l=arguments.length>1&&arguments[1]!==void 0?arguments[1]:{},d=null,y=null,v=null,C=null;if(er=!x,er&&(x="<!-->"),typeof x!="string"&&!Vt(x)&&(x=qc(x),typeof x!="string"))throw We("dirty is not a string, aborting");if(!e.isSupported)return x;Se?(J=Et,T=At):ar(l),(K.uponSanitizeElement.length>0||K.uponSanitizeAttribute.length>0)&&(J=Te(J)),K.uponSanitizeAttribute.length>0&&(T=Te(T)),e.removed=[];let I=Qn&&typeof x!="string"&&Vt(x),U=[],ce=ct;if(I){zo(x);let ve=ie(x);if(typeof ve=="string"){let Lt=oe(ve);if(!J[Lt]||V[Lt])throw sr(x),We("root node is forbidden and cannot be sanitized in-place")}if(vn(x))throw sr(x),We("root node is clobbered and cannot be sanitized in-place");U=lr(x),ct=Dr()}else if(Vt(x))d=ka("<!---->"),y=d.ownerDocument.importNode(x,!0),y.nodeType===le.element&&y.nodeName==="BODY"||y.nodeName==="HTML"?d=y:d.appendChild(y),pr(d);else{if(!St&&!O&&!ee&&x.indexOf("<")===-1)return se&&mn?k(x):x;if(d=ka(x),!d)return St?null:mn?ye:""}d&&Jn&&Qe(d.firstChild);let je=I?x:d;try{I&&pr(x);let ve=cr(je);for(;v=ve.nextNode();)dr(v,je),hr(v,je),et(v.content)&&qt(v.content);I&&Io(x,U)}catch(ve){throw I&&(sr(x),Sa(x,U)),ve}finally{ct=ce}if(I){if(Sa(x,U))throw We("a node selected for removal could not be safely returned; refusing to sanitize in place");return O&&ur(x),x}if(St){if(O&&ur(d),fn)for(C=Y.call(d.ownerDocument);d.firstChild;)C.appendChild(d.firstChild);else C=d;return(T.shadowroot||T.shadowrootmode)&&(C=Q.call(r,C,!0)),C}let be=ee?d.outerHTML:d.innerHTML;return ee&&J["!doctype"]&&d.ownerDocument&&d.ownerDocument.doctype&&d.ownerDocument.doctype.name&&pe(au,d.ownerDocument.doctype.name)&&(be="<!DOCTYPE "+d.ownerDocument.doctype.name+`>
`+be),O&&(be=yn(be)),se&&mn?k(be):be},e.setConfig=function(){let x=arguments.length>0&&arguments[0]!==void 0?arguments[0]:{};ar(x),Se=!0,Et=J,At=T},e.clearConfig=function(){Nt=null,Se=!1,Et=null,At=null,se=Be,ye=""},e.isValidAttribute=function(x,l,d){Nt||ar({});let y=oe(x),v=oe(l);return typeof d=="string"&&(Ra(l,d)||!N&&pe(Ei,d))?!1:Ma(y,v,d)},e.addHook=function(x,l){typeof l=="function"&&we(K,x)&&tn(K[x],l)},e.removeHook=function(x,l){if(we(K,x)){if(l!==void 0){let d=Uc(K[x],l);return d===-1?void 0:Fc(K[x],d,1)[0]}return hi(K[x])}},e.removeHooks=function(x){we(K,x)&&(K[x]=[])},e.removeAllHooks=function(){K=Ai()},e}var Pn=Mi();var Li="vitrine",wh=Object.freeze(["a","abbr","b","blockquote","br","caption","code","col","colgroup","dd","del","details","div","dl","dt","em","figcaption","figure","h1","h2","h3","h4","h5","h6","hr","i","img","input","ins","kbd","li","mark","ol","p","pre","q","s","samp","small","span","strong","sub","summary","sup","table","tbody","td","tfoot","th","thead","tr","u","ul","var"]),Eh=Object.freeze(["align","alt","checked","class","colspan","dir","disabled","height","href","lang","open","rowspan","span","src","start","title","type","width"]);var sn;function qr(){if(sn!==void 0)return sn;sn=null;let n=globalThis.trustedTypes;if(n&&typeof n.createPolicy=="function")try{sn=n.createPolicy(Li,{createHTML:e=>e,createScriptURL:e=>e})}catch{console.warn(`[vitrine] Could not create the "${Li}" Trusted Types policy. Add it to your CSP "trusted-types" directive.`)}return sn??null}function uu(n){let e=document.createDocumentFragment();return e.append(document.createTextNode(String(n))),e}var bt;function du(){if(bt!==void 0)return bt;bt=!1;try{if(!Pn.isSupported)return!1;let n=Pn.sanitize('<b>1</b><script>1<\/script><a href="javascript:1">a</a>',{RETURN_DOM_FRAGMENT:!0,...qr()?{TRUSTED_TYPES_POLICY:qr()}:{}});bt=n instanceof DocumentFragment&&n.querySelector("b")!==null&&n.querySelector("script")===null&&!n.querySelector("a")?.hasAttribute("href")}catch{bt=!1}return bt||console.warn("[vitrine] HTML sanitizer unavailable: rich content is shown as plain text."),bt}var hu=/^(?:hljs-[\w-]{1,40}|[a-z]{1,20}_{1,2})$/;function Ri(n){if(!du())return uu(n);let e=qr(),t={ALLOWED_TAGS:["span"],ALLOWED_ATTR:["class"],ALLOW_DATA_ATTR:!1,ALLOW_ARIA_ATTR:!1,RETURN_DOM_FRAGMENT:!0,KEEP_CONTENT:!0};e&&(t.TRUSTED_TYPES_POLICY=e);let r=Pn.sanitize(String(n),t);for(let a of Array.from(r.querySelectorAll("[class]"))){let s=Array.from(a.classList).filter(i=>hu.test(i));s.length?a.setAttribute("class",s.join(" ")):a.removeAttribute("class")}return r}var Ah=Object.freeze(["script","style","iframe","object","embed","form","input","button","textarea","select","link","meta","base","img","image","video","audio","source","animate","animateMotion","animateTransform","set","feImage"]);var pu={bash:Zs,diff:Js,javascript:ni,json:ri,markdown:ai,plaintext:si,python:ii,shell:oi,xml:li,yaml:ci};for(let[n,e]of Object.entries(pu))He.registerLanguage(n,e);He.configure({ignoreUnescapedHTML:!0,throwUnescapedHTML:!1});var fu=4e3,yt=null,Oi=new Map,mu=1e4;function Ii(n){if(typeof n!="string")return null;let e=n.trim().toLowerCase();if(!e||e.length>40)return null;if(Object.prototype.hasOwnProperty.call(On,e))return e;if(!yt){yt=new Map;for(let[t,r]of Object.entries(On))for(let a of r.split(" "))a&&!yt.has(a)&&yt.set(a,t);yt.set("text","plaintext"),yt.set("plain","plaintext")}return yt.get(e)??null}function zn(n){return!!He.getLanguage(n)}function Di(n){if(zn(n))return Promise.resolve(!0);if(!Object.prototype.hasOwnProperty.call(On,n))return Promise.resolve(!1);let e=Oi.get(n);if(e)return e;let t=gu(n);return Oi.set(n,t),t}async function gu(n){let e=W().languagesUrl||ps();if(!e)return!1;try{let t=new URL(`${n}.js`,new URL(e.endsWith("/")?e:`${e}/`,document.baseURI));if(t.protocol!=="https:"&&t.protocol!=="http:")return!1;let r=await import(t.href);return typeof r.default!="function"?!1:(He.registerLanguage(n,r.default),!0)}catch(t){return console.warn(`[vitrine] Could not load the "${n}" language.`,t),!1}}function Pi(n){let e=He.listLanguages().filter(r=>r!=="plaintext"),t=He.highlightAuto(n.slice(0,fu),e);return t.language&&t.relevance>=3?t.language:"plaintext"}function bu(n){for(let e=0;e<n.length;){let t=n.indexOf(`
`,e),r=t===-1?n.length:t;if(r-e>mu)return!0;e=r+1}return!1}function zi(n,e){if(e==="plaintext"||!zn(e)||bu(n)){let r=document.createDocumentFragment();return r.append(document.createTextNode(n)),r}let t=He.highlight(n,{language:e,ignoreIllegals:!0});return Ri(t.value)}function Bi(n){let e=[],t=[],r=document.createDocumentFragment(),a=r,s=()=>{e.push(r),r=document.createDocumentFragment(),a=r;for(let o of t){let c=o.cloneNode(!1);a.appendChild(c),a=c}},i=o=>{if(o.nodeType===Node.TEXT_NODE){(o.nodeValue??"").split(`
`).forEach((h,b)=>{b>0&&s(),h&&a.appendChild(document.createTextNode(h))});return}if(o.nodeType!==Node.ELEMENT_NODE)return;let c=o;a.appendChild(c.cloneNode(!1)),a=a.lastChild,t.push(c);for(let u of Array.from(c.childNodes))i(u);t.pop(),a=a.parentNode};for(let o of Array.from(n.childNodes))i(o);return e.push(r),e}var yu=1e3,Ui=200;function vu(n){let e=[],t=[];for(let r of n)r.startsWith("@@")?(e.push("hunk"),t.push(r)):/^(?:\+\+\+|---)(?: |$)|^diff |^index /.test(r)?(e.push("meta"),t.push(r)):r.startsWith("+")?(e.push("added"),t.push(r.slice(1))):r.startsWith("-")?(e.push("removed"),t.push(r.slice(1))):(e.push("context"),t.push(r.startsWith(" ")?r.slice(1):r));return{kinds:e,code:t}}function Bn(n,e){let r=(n.endsWith(`
`)&&!e.trailingNewline?n.slice(0,-1):n).split(`
`),a=null;if(e.diff){let D=vu(r);a=D.kinds,r=D.code}let s=r.join(`
`),i=s.length>e.highlightLimit,o=i||e.language==="plaintext",c=o?null:Bi(zi(s,e.language)),u=o?s.split(`
`):null,h=c?c.length:u.length,b=e.startLine+h-1,m=Math.max(String(e.startLine).length,String(b).length),_=f("pre",{class:"code",part:"code"});_.style.setProperty("--_digits",String(m));let p=D=>{let j=e.startLine+D,P=a?.[D],q=f("span",{class:"line",part:"line",attrs:{"data-line":j}});if(e.highlightRanges.length&&Pa(j,e.highlightRanges)&&(q.classList.add("highlighted"),q.setAttribute("part","line line-highlighted")),P&&P!=="context"&&q.classList.add(P),e.lineNumbers&&q.append(f("span",{class:"gutter",part:"gutter line-number",attrs:{"aria-hidden":"true","data-n":j}})),a){let ae=P==="added"?e.diffLabels?.added:P==="removed"?e.diffLabels?.removed:"";q.append(f("span",{class:"sign"},ae?f("span",{class:"sr-only",text:`${ae}: `}):null))}let X=f("span",{class:"content"});return c?X.append(c[D]):u?.[D]&&X.append(u[D]),D<h-1&&X.append(`
`),q.append(X),q},g=(D,j,P)=>{let q=document.createDocumentFragment();for(let X=j;X<P;X+=1)q.appendChild(p(X));D.appendChild(q)},S=document.createDocumentFragment();if(e.chunk!==!1&&h>yu)for(let D=0;D<h;D+=Ui){let j=Math.min(h,D+Ui),P=f("span",{class:"chunk",attrs:{"data-first":e.startLine+D,"data-count":j-D}});P.style.setProperty("--_chunk-lines",String(j-D)),S.append(P),D===0?g(P,D,j):(P.setAttribute("data-pending",""),_s(P,()=>{P.removeAttribute("data-pending"),g(P,D,j)}))}else g(S,0,h);return _.append(S),{element:f("div",{class:"code-view"},_),code:_,lineCount:h,highlightSkipped:i}}function Kr(n){n&&(n.closest(".chunk")?.classList.add("revealed"),n.scrollIntoView({block:"nearest",inline:"nearest"}))}var Un=class{constructor(e){this.steps=[{value:e,start:0,end:0}],this.index=0,this.lastKind="",this.lastTime=0,this.listeners=new Set}get canUndo(){return this.index>0}get canRedo(){return this.index<this.steps.length-1}get current(){return this.steps[this.index]}record(e,t){if(e.value===this.current.value)return;let r=Date.now(),s=(t==="insertText"||t.startsWith("delete"))&&t===this.lastKind&&r-this.lastTime<600&&!this.canRedo;this.steps.length=this.index+1,s&&this.index>0?this.steps[this.index]=e:(this.steps.push(e),this.index+=1),this.lastKind=t,this.lastTime=r,this.trim(),this.notify()}undo(){return this.canUndo?(this.index-=1,this.lastKind="",this.notify(),this.current):null}redo(){return this.canRedo?(this.index+=1,this.lastKind="",this.notify(),this.current):null}trim(){let e=this.steps.reduce((t,r)=>t+r.value.length,0);for(;this.steps.length>1&&(this.steps.length>300||e>2e7)&&this.index>0;)e-=this.steps.shift().value.length,this.index-=1}subscribe(e){return this.listeners.add(e),()=>this.listeners.delete(e)}notify(){for(let e of this.listeners)e()}};var xu=6e4,_u=250,jn="  ",Ge=class{constructor(e){this.options=e,this.text=e.text,this.tabReleased=!1,this.changedSinceFocus=!1,this.timer=void 0,this.textarea=f("textarea",{class:"editor-input",part:"editor",attrs:{"aria-label":e.label,placeholder:e.placeholder??null,spellcheck:"false",autocapitalize:"off",autocomplete:"off",autocorrect:"off",wrap:e.wrap?"soft":"off","data-focus-key":"editor"}}),this.textarea.value=e.text,this.history=e.history&&e.history.current.value===e.text?e.history:new Un(e.text),this.layer=this.buildLayer(e.text),this.element=f("div",{class:e.wrap?"editor wrap":"editor"},this.layer,this.textarea),this.textarea.addEventListener("input",t=>this.onInput(t.inputType||"other")),this.textarea.addEventListener("beforeinput",t=>{(t.inputType==="historyUndo"||t.inputType==="historyRedo")&&(t.preventDefault(),t.inputType==="historyUndo"?this.undo():this.redo())}),this.textarea.addEventListener("keydown",t=>this.onKeyDown(t)),this.textarea.addEventListener("focus",()=>{this.changedSinceFocus=!1}),this.textarea.addEventListener("blur",()=>{this.changedSinceFocus&&e.onChange?.(this.text)})}buildLayer(e){let t=Bn(e,{language:this.options.language,lineNumbers:this.options.lineNumbers,startLine:1,highlightRanges:this.options.highlightRanges??[],diff:!1,highlightLimit:this.options.highlightLimit,trailingNewline:!0,chunk:!1});return t.element.classList.add("editor-layer"),t.element.setAttribute("aria-hidden","true"),t.element}refresh(){clearTimeout(this.timer);let e=this.buildLayer(this.text);this.layer.replaceWith(e),this.layer=e,this.element.classList.remove("pending"),this.align()}align(){let e=this.layer.querySelector(".gutter"),t=e?e.getBoundingClientRect().width:0;this.element.style.setProperty("--_editor-gutter",`${t}px`)}setHighlightRanges(e){this.options.highlightRanges=e,this.refresh()}onInput(e){this.text=this.textarea.value.replace(/\r\n?/g,`
`),this.changedSinceFocus=!0,this.history.record({value:this.text,start:this.textarea.selectionStart,end:this.textarea.selectionEnd},e),this.text.length<=xu?this.refresh():(this.element.classList.add("pending"),clearTimeout(this.timer),this.timer=setTimeout(()=>this.refresh(),_u)),this.options.onInput(this.text)}onKeyDown(e){let t=e.ctrlKey||e.metaKey,r=e.key.toLowerCase();if(t&&!e.altKey&&(r==="z"||r==="y")){e.preventDefault(),r==="y"||e.shiftKey?this.redo():this.undo();return}if(e.key==="Escape"){this.tabReleased=!0;return}if(e.key==="Tab"&&!this.tabReleased&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault(),e.shiftKey?this.outdent():this.indent();return}if(e.key!=="Tab"&&(this.tabReleased=!1),e.key==="Enter"&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey&&!e.isComposing){let{value:a,selectionStart:s}=this.textarea,i=a.lastIndexOf(`
`,s-1)+1,o=/^[ \t]*/.exec(a.slice(i,s))?.[0]??"";o&&(e.preventDefault(),this.insert(`
${o}`))}}indent(){let{value:e,selectionStart:t,selectionEnd:r}=this.textarea;if(t===r||!e.slice(t,r).includes(`
`)){this.insert(jn);return}let a=e.lastIndexOf(`
`,t-1)+1,s=e.slice(a,r),i=s.replace(/^/gm,jn);this.replaceRange(a,r,i),this.textarea.setSelectionRange(t+jn.length,r+(i.length-s.length))}outdent(){let{value:e,selectionStart:t,selectionEnd:r}=this.textarea,a=e.lastIndexOf(`
`,t-1)+1,s=e.slice(a,r),i=new RegExp(`^(?:\\t| {1,${jn.length}})`,"gm"),o=(/^(?:\t| {1,2})/.exec(s)?.[0]??"").length,c=s.replace(i,"");c!==s&&(this.replaceRange(a,r,c),this.textarea.setSelectionRange(Math.max(a,t-o),r-(s.length-c.length)))}insert(e){this.textarea.focus(),document.execCommand?.("insertText",!1,e)||(this.textarea.setRangeText(e,this.textarea.selectionStart,this.textarea.selectionEnd,"end"),this.onInput("insertText"))}replaceRange(e,t,r){this.textarea.setSelectionRange(e,t),this.insert(r)}undo(){this.restore(this.history.undo())}redo(){this.restore(this.history.redo())}restore(e){e&&(this.textarea.value=e.value,this.textarea.focus(),this.textarea.setSelectionRange(e.start,e.end),this.text=e.value,this.changedSinceFocus=!0,this.refresh(),this.options.onInput(this.text))}destroy(){clearTimeout(this.timer)}};var ji=Object.freeze({mapRole:"map",mapSummary:"World map, {projection} projection: {places} places, {countries} countries highlighted, {routes} routes.",mapKeyboardHelp:"Drag or use the arrow keys to move, the wheel or + and - to zoom, 0 to reset. The list under the map gives every item.",mapProjection:"Projection","mapProjection_natural-earth":"Natural Earth","mapProjection_equal-earth":"Equal Earth",mapProjection_mercator:"Mercator",mapProjection_equirectangular:"Equirectangular",mapProjection_globe:"Globe (3D)","mapProjection_azimuthal-equal-area":"Azimuthal equal-area","mapProjection_azimuthal-equidistant":"Azimuthal equidistant",mapProjection_stereographic:"Stereographic",mapProjection_gnomonic:"Gnomonic","mapProjection_transverse-mercator":"Transverse Mercator","mapProjection_conic-equal-area":"Conic equal-area","mapProjection_conic-conformal":"Conic conformal",mapBasemap:"Map style",mapBasemap_light:"Light",mapBasemap_dark:"Dark",mapBasemap_political:"Political",mapBasemap_satellite:"Seen from the sky",mapBasemap_night:"Night",mapBasemap_blueprint:"Blueprint",mapBasemap_vintage:"Vintage",mapBasemap_mono:"Monochrome",mapGraticule:"Grid",mapSearch:"Find a place",mapSearchPlaceholder:"Coordinates, city, country or address",mapZoomIn:"Zoom in",mapZoomOut:"Zoom out",mapReset:"Reset the view",mapPlaces:"{count} places",mapCopyPlaces:"Copy the places",mapLegend:"Color scale",mapList:"Places, countries and routes",mapKind_marker:"Place",mapKind_country:"Country",mapKind_route:"Route",mapKind_shape:"Shape",mapKind_pin:"Pin",mapShow:"Show {label} on the map",mapShape:"Shape",mapDistance:"{km} km",mapLocating:"Locating\u2026",mapNeedsGeocoder:"Address: needs a geocoder",mapNoGeocoder:"\u201C{query}\u201D is an address: this map has no geocoder (geocoder attribute).",mapGeocoding:"Looking for \u201C{query}\u201D\u2026",mapNotFound:"Nothing found for \u201C{query}\u201D.",mapFound:"{label}: {coords}",mapFoundCountry:"{name}",mapSelectedPoint:"{label} selected, {coords}",mapSelectedCountry:"{name} selected",mapInvalidLines:"Lines not understood: {list}",mapLoadFailed:"The map could not be loaded: {message}",mapTrack:"Track the target",mapTracking:"Tracking {label}\u2026",mapTargetLocated:"Target located: {label}, {coords}",mapStop:"Stop"}),Fi={mapRole:"carte",mapSummary:"Carte du monde, projection {projection} : {places} lieux, {countries} pays mis en avant, {routes} trajets.",mapKeyboardHelp:"Glissez ou utilisez les fl\xE8ches pour vous d\xE9placer, la molette ou + et - pour zoomer, 0 pour revenir au d\xE9part. La liste sous la carte donne chaque \xE9l\xE9ment.",mapProjection:"Projection",mapProjection_globe:"Globe (3D)",mapProjection_equirectangular:"\xC9quirectangulaire","mapProjection_azimuthal-equal-area":"Azimutale \xE9quivalente","mapProjection_azimuthal-equidistant":"Azimutale \xE9quidistante",mapProjection_stereographic:"St\xE9r\xE9ographique",mapProjection_gnomonic:"Gnomonique","mapProjection_transverse-mercator":"Mercator transverse","mapProjection_conic-equal-area":"Conique \xE9quivalente","mapProjection_conic-conformal":"Conique conforme",mapBasemap:"Style",mapBasemap_light:"Clair",mapBasemap_dark:"Sombre",mapBasemap_political:"Politique",mapBasemap_satellite:"Vue du ciel",mapBasemap_night:"Nuit",mapBasemap_blueprint:"Plan",mapBasemap_vintage:"Ancien",mapBasemap_mono:"Monochrome",mapGraticule:"Grille",mapSearch:"Trouver un lieu",mapSearchPlaceholder:"Coordonn\xE9es, ville, pays ou adresse",mapZoomIn:"Zoomer",mapZoomOut:"D\xE9zoomer",mapReset:"Revenir \xE0 la vue de d\xE9part",mapPlaces:"{count} lieux",mapCopyPlaces:"Copier les lieux",mapLegend:"\xC9chelle de couleurs",mapList:"Lieux, pays et trajets",mapKind_marker:"Lieu",mapKind_country:"Pays",mapKind_route:"Trajet",mapKind_shape:"Forme",mapKind_pin:"Rep\xE8re",mapShow:"Montrer {label} sur la carte",mapShape:"Forme",mapDistance:"{km} km",mapLocating:"Recherche\u2026",mapNeedsGeocoder:"Adresse : il faut un g\xE9ocodeur",mapNoGeocoder:"\xAB {query} \xBB est une adresse : cette carte n\u2019a pas de g\xE9ocodeur (attribut geocoder).",mapGeocoding:"Recherche de \xAB {query} \xBB\u2026",mapNotFound:"Rien trouv\xE9 pour \xAB {query} \xBB.",mapSelectedPoint:"{label} s\xE9lectionn\xE9, {coords}",mapSelectedCountry:"{name} s\xE9lectionn\xE9",mapInvalidLines:"Lignes non comprises : {list}",mapLoadFailed:"La carte n\u2019a pas pu \xEAtre charg\xE9e : {message}",mapTrack:"Traquer la cible",mapTracking:"Traque de {label}\u2026",mapTargetLocated:"Cible localis\xE9e : {label}, {coords}",mapStop:"Arr\xEAter"};var wu="004AFAFG 008ALALB 010AQATA 012DZDZA 024AOAGO 031AZAZE 032ARARG 036AUAUS 040ATAUT 044BSBHS 050BDBGD 051AMARM 056BEBEL 064BTBTN 068BOBOL 070BABIH 072BWBWA 076BRBRA 084BZBLZ 090SBSLB 096BNBRN 100BGBGR 104MMMMR 108BIBDI 112BYBLR 116KHKHM 120CMCMR 124CACAN 140CFCAF 144LKLKA 148TDTCD 152CLCHL 156CNCHN 158TWTWN 170COCOL 178CGCOG 180CDCOD 188CRCRI 191HRHRV 192CUCUB 196CYCYP 203CZCZE 204BJBEN 208DKDNK 214DODOM 218ECECU 222SVSLV 226GQGNQ 231ETETH 232ERERI 233EEEST 238FKFLK 242FJFJI 246FIFIN 250FRFRA 260TFATF 262DJDJI 266GAGAB 268GEGEO 270GMGMB 275PSPSE 276DEDEU 288GHGHA 300GRGRC 304GLGRL 320GTGTM 324GNGIN 328GYGUY 332HTHTI 340HNHND 348HUHUN 352ISISL 356ININD 360IDIDN 364IRIRN 368IQIRQ 372IEIRL 376ILISR 380ITITA 384CICIV 388JMJAM 392JPJPN 398KZKAZ 400JOJOR 404KEKEN 408KPPRK 410KRKOR 414KWKWT 417KGKGZ 418LALAO 422LBLBN 426LSLSO 428LVLVA 430LRLBR 434LYLBY 440LTLTU 442LULUX 450MGMDG 454MWMWI 458MYMYS 466MLMLI 478MRMRT 484MXMEX 496MNMNG 498MDMDA 499MEMNE 504MAMAR 508MZMOZ 512OMOMN 516NANAM 524NPNPL 528NLNLD 540NCNCL 548VUVUT 554NZNZL 558NINIC 562NENER 566NGNGA 578NONOR 586PKPAK 591PAPAN 598PGPNG 600PYPRY 604PEPER 608PHPHL 616PLPOL 620PTPRT 624GWGNB 626TLTLS 630PRPRI 634QAQAT 642ROROU 643RURUS 646RWRWA 682SASAU 686SNSEN 688RSSRB 694SLSLE 703SKSVK 704VNVNM 705SISVN 706SOSOM 710ZAZAF 716ZWZWE 724ESESP 728SSSSD 729SDSDN 732EHESH 740SRSUR 748SZSWZ 752SESWE 756CHCHE 760SYSYR 762TJTJK 764THTHA 768TGTGO 780TTTTO 784AEARE 788TNTUN 792TRTUR 795TMTKM 800UGUGA 804UAUKR 807MKMKD 818EGEGY 826GBGBR 834TZTZA 840USUSA 854BFBFA 858UYURY 860UZUZB 862VEVEN 887YEYEM 894ZMZMB",Gi=Object.freeze({Kosovo:["XK","XKX"],"N. Cyprus":["","CYN"],Somaliland:["","SOL"]}),on=new Map,Ye=new Map;for(let n of wu.split(" ")){let e={numeric:n.slice(0,3),a2:n.slice(3,5),a3:n.slice(5,8)};on.set(e.numeric,e),Ye.set(e.a2,e),Ye.set(e.a3,e)}for(let[n,[e,t]]of Object.entries(Gi)){let r={numeric:n,a2:e,a3:t};on.set(n,r),e&&Ye.set(e,r),Ye.set(t,r)}var Eu=Object.freeze({usa:"US","united states of america":"US",america:"US","etats-unis":"US","etats unis":"US",uk:"GB","great britain":"GB",britain:"GB",england:"GB",scotland:"GB",wales:"GB",angleterre:"GB","grande-bretagne":"GB","royaume uni":"GB",holland:"NL","czech republic":"CZ","republique tcheque":"CZ","ivory coast":"CI","cote divoire":"CI",drc:"CD","dr congo":"CD","congo-kinshasa":"CD","congo kinshasa":"CD","congo-brazzaville":"CG",burma:"MM",swaziland:"SZ",eswatini:"SZ",macedonia:"MK","north macedonia":"MK","south korea":"KR","north korea":"KP","coree du sud":"KR","coree du nord":"KP",russia:"RU","russian federation":"RU","east timor":"TL","cape verde":"CV",vatican:"VA",persia:"IR","western sahara":"EH","w. sahara":"EH",bosnia:"BA","bosnia and herzegovina":"BA",turkiye:"TR","the netherlands":"NL","the bahamas":"BS"});function vt(n){return n.normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/[’'`.]/g,"").replace(/[\s_]+/g," ").trim()}var $i=new Map;function Hi(n){let e=n.split("-")[0]||"en",t=$i.get(e);if(t)return t;let r=new Map(Object.entries(Eu));for(let a of new Set(["en","fr",e])){let s=Vi(a);if(s)for(let{a2:i}of Ye.values()){if(!i)continue;let o=s.of(i);o&&o!==i&&r.set(vt(o),i)}}return $i.set(e,r),r}var Fn=new Map;function Vi(n){if(!Fn.has(n))try{Fn.set(n,new Intl.DisplayNames([n],{type:"region"}))}catch{Fn.set(n,null)}return Fn.get(n)??null}function $n(n,e=""){return on.get(n??e)??on.get(e)??{numeric:n??e,a2:"",a3:""}}function Ze(n,e="en"){let t=n.trim();if(!t)return null;if(/^[A-Za-z]{2,3}$/.test(t)&&Ye.has(t.toUpperCase())&&(t===t.toUpperCase()||!Hi(e).has(vt(t))))return Ye.get(t.toUpperCase())??null;if(/^\d{3}$/.test(t))return on.get(t)??null;let r=vt(t),a=Hi(e).get(r);if(a)return Ye.get(a)??null;for(let[s,i]of Object.entries(Gi))if(vt(s)===r)return Ye.get(i[1])??null;return null}function Me(n,e,t=""){if(!n.a2)return t||n.a3;let r=Vi(e)?.of(n.a2);return r&&r!==n.a2?r:t||n.a2}function Wr(n){return/^[A-Z]{2}$/.test(n)?String.fromCodePoint(...[...n].map(e=>127462+e.charCodeAt(0)-65)):""}var Au=`Paris|FR|48.8566|2.3522
Lyon|FR|45.764|4.8357
Marseille|FR|43.2965|5.3698
Toulouse|FR|43.6047|1.4442
Bordeaux|FR|44.8378|-0.5792
Lille|FR|50.6292|3.0573
Nice|FR|43.7102|7.262
Strasbourg|FR|48.5734|7.7521
Nantes|FR|47.2184|-1.5536
London,Londres|GB|51.5072|-0.1276
Manchester|GB|53.4808|-2.2426
Edinburgh,\xC9dimbourg|GB|55.9533|-3.1883
Dublin|IE|53.3498|-6.2603
Brussels,Bruxelles|BE|50.8503|4.3517
Luxembourg|LU|49.6116|6.1319
Amsterdam|NL|52.3676|4.9041
Rotterdam|NL|51.9244|4.4777
The Hague,La Haye|NL|52.0705|4.3007
Berlin|DE|52.52|13.405
Munich,M\xFCnchen|DE|48.1351|11.582
Frankfurt,Francfort|DE|50.1109|8.6821
Hamburg,Hambourg|DE|53.5511|9.9937
Cologne,K\xF6ln|DE|50.9375|6.9603
Zurich,Z\xFCrich|CH|47.3769|8.5417
Geneva,Gen\xE8ve|CH|46.2044|6.1432
Bern,Berne|CH|46.948|7.4474
Vienna,Vienne,Wien|AT|48.2082|16.3738
Prague,Praha|CZ|50.0755|14.4378
Warsaw,Varsovie,Warszawa|PL|52.2297|21.0122
Budapest|HU|47.4979|19.0402
Bratislava|SK|48.1486|17.1077
Ljubljana|SI|46.0569|14.5058
Zagreb|HR|45.815|15.9819
Belgrade,Beograd|RS|44.7866|20.4489
Bucharest,Bucarest|RO|44.4268|26.1025
Sofia|BG|42.6977|23.3219
Athens,Ath\xE8nes|GR|37.9838|23.7275
Rome,Roma|IT|41.9028|12.4964
Milan,Milano|IT|45.4642|9.19
Naples,Napoli|IT|40.8518|14.2681
Venice,Venise,Venezia|IT|45.4408|12.3155
Madrid|ES|40.4168|-3.7038
Barcelona,Barcelone|ES|41.3874|2.1686
Seville,S\xE9ville,Sevilla|ES|37.3891|-5.9845
Valencia,Valence|ES|39.4699|-0.3763
Lisbon,Lisbonne,Lisboa|PT|38.7223|-9.1393
Porto|PT|41.1579|-8.6291
Copenhagen,Copenhague|DK|55.6761|12.5683
Oslo|NO|59.9139|10.7522
Stockholm|SE|59.3293|18.0686
Helsinki|FI|60.1699|24.9384
Reykjavik,Reykjav\xEDk|IS|64.1466|-21.9426
Tallinn|EE|59.437|24.7536
Riga|LV|56.9496|24.1052
Vilnius|LT|54.6872|25.2797
Kyiv,Kiev|UA|50.4501|30.5234
Minsk|BY|53.9006|27.559
Moscow,Moscou|RU|55.7558|37.6173
Saint Petersburg,Saint-P\xE9tersbourg|RU|59.9311|30.3609
Istanbul|TR|41.0082|28.9784
Ankara|TR|39.9334|32.8597
Tbilisi|GE|41.7151|44.8271
Yerevan,Erevan|AM|40.1792|44.4991
Baku,Bakou|AZ|40.4093|49.8671
Tehran,T\xE9h\xE9ran|IR|35.6892|51.389
Baghdad,Bagdad|IQ|33.3152|44.3661
Riyadh,Riyad|SA|24.7136|46.6753
Jeddah,Djeddah|SA|21.4858|39.1925
Dubai,Duba\xEF|AE|25.2048|55.2708
Abu Dhabi|AE|24.4539|54.3773
Doha|QA|25.2854|51.531
Jerusalem,J\xE9rusalem|IL|31.7683|35.2137
Tel Aviv|IL|32.0853|34.7818
Beirut,Beyrouth|LB|33.8938|35.5018
Amman|JO|31.9454|35.9284
Cairo,Le Caire|EG|30.0444|31.2357
Casablanca|MA|33.5731|-7.5898
Rabat|MA|34.0209|-6.8416
Algiers,Alger|DZ|36.7538|3.0588
Tunis|TN|36.8065|10.1815
Dakar|SN|14.7167|-17.4677
Abidjan|CI|5.36|-4.0083
Lagos|NG|6.5244|3.3792
Abuja|NG|9.0765|7.3986
Accra|GH|5.6037|-0.187
Kinshasa|CD|-4.4419|15.2663
Nairobi|KE|-1.2921|36.8219
Addis Ababa,Addis-Abeba|ET|8.9806|38.7578
Kampala|UG|0.3476|32.5825
Dar es Salaam|TZ|-6.7924|39.2083
Luanda|AO|-8.839|13.2894
Johannesburg|ZA|-26.2041|28.0473
Cape Town,Le Cap|ZA|-33.9249|18.4241
Antananarivo|MG|-18.8792|47.5079
Karachi|PK|24.8607|67.0011
Islamabad|PK|33.6844|73.0479
Kabul|AF|34.5553|69.2075
New Delhi,Delhi|IN|28.6139|77.209
Mumbai,Bombay|IN|19.076|72.8777
Bangalore,Bengaluru|IN|12.9716|77.5946
Kolkata,Calcutta|IN|22.5726|88.3639
Chennai|IN|13.0827|80.2707
Dhaka|BD|23.8103|90.4125
Kathmandu,Katmandou|NP|27.7172|85.324
Colombo|LK|6.9271|79.8612
Bangkok|TH|13.7563|100.5018
Hanoi|VN|21.0278|105.8342
Ho Chi Minh City,H\xF4 Chi Minh-Ville,Saigon|VN|10.8231|106.6297
Kuala Lumpur|MY|3.139|101.6869
Singapore,Singapour|SG|1.3521|103.8198
Jakarta|ID|-6.2088|106.8456
Manila,Manille|PH|14.5995|120.9842
Beijing,P\xE9kin|CN|39.9042|116.4074
Shanghai|CN|31.2304|121.4737
Hong Kong|HK|22.3193|114.1694
Shenzhen|CN|22.5431|114.0579
Taipei|TW|25.033|121.5654
Seoul,S\xE9oul|KR|37.5665|126.978
Pyongyang|KP|39.0392|125.7625
Tokyo|JP|35.6762|139.6503
Osaka|JP|34.6937|135.5023
Ulaanbaatar,Oulan-Bator|MN|47.8864|106.9057
Astana|KZ|51.1694|71.4491
Tashkent,Tachkent|UZ|41.2995|69.2401
Sydney|AU|-33.8688|151.2093
Melbourne|AU|-37.8136|144.9631
Brisbane|AU|-27.4698|153.0251
Perth|AU|-31.9505|115.8605
Canberra|AU|-35.2809|149.13
Auckland|NZ|-36.8485|174.7633
Wellington|NZ|-41.2865|174.7762
Honolulu|US|21.3069|-157.8583
Anchorage|US|61.2181|-149.9003
Washington,Washington DC|US|38.9072|-77.0369
New York,New York City,NYC|US|40.7128|-74.006
Boston|US|42.3601|-71.0589
Chicago|US|41.8781|-87.6298
Miami|US|25.7617|-80.1918
Atlanta|US|33.749|-84.388
Houston|US|29.7604|-95.3698
Dallas|US|32.7767|-96.797
Denver|US|39.7392|-104.9903
Seattle|US|47.6062|-122.3321
San Francisco|US|37.7749|-122.4194
Los Angeles|US|34.0522|-118.2437
Las Vegas|US|36.1699|-115.1398
Toronto|CA|43.6532|-79.3832
Montreal,Montr\xE9al|CA|45.5019|-73.5674
Quebec City,Qu\xE9bec|CA|46.8139|-71.208
Vancouver|CA|49.2827|-123.1207
Ottawa|CA|45.4215|-75.6972
Mexico City,Mexico,Ciudad de M\xE9xico|MX|19.4326|-99.1332
Havana,La Havane|CU|23.1136|-82.3666
Panama City,Panama|PA|8.9824|-79.5199
Bogot\xE1,Bogota|CO|4.711|-74.0721
Caracas|VE|10.4806|-66.9036
Lima|PE|-12.0464|-77.0428
Quito|EC|-0.1807|-78.4678
Santiago|CL|-33.4489|-70.6693
Buenos Aires|AR|-34.6037|-58.3816
Montevideo|UY|-34.9011|-56.1645
S\xE3o Paulo,Sao Paulo|BR|-23.5505|-46.6333
Rio de Janeiro|BR|-22.9068|-43.1729
Bras\xEDlia,Brasilia|BR|-15.7975|-47.8919
La Paz|BO|-16.4897|-68.1193
Nuuk|GL|64.1814|-51.6941
North Pole,P\xF4le Nord|AQ|90|0
South Pole,P\xF4le Sud|AQ|-90|0`,ln=null;function qi(n){if(!ln){ln=new Map;for(let t of Au.split(`
`)){let[r,a,s,i]=t.split("|"),o=r.split(","),c={name:o[0],country:a,lat:Number(s),lon:Number(i)};for(let u of o)ln.set(vt(u),c)}}let e=vt(n);return ln.get(e)??ln.get(e.replace(/,.*$/,"").trim())??null}var Yr=2e3,Zr=/^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i,Ki=/\s*(?:->|→|=>|⟶)\s*/;function Jr(n,e="en"){let t=n.trim();if(/^[[{]/.test(t))try{return Tu(JSON.parse(t),e)}catch{}let r=[],a=[];for(let s of t.split(/\r?\n/)){let i=s.trim();if(!i||i.startsWith("//")||i.startsWith("; "))continue;if(r.length>=Yr)break;let o=Su(i,e);o?r.push(o):a.push(i)}return{items:r,invalid:a,view:{}}}function Su(n,e="en"){let t=n,r="",a=t.match(/\s+(#[0-9a-f]{3,8})$/i)??t.match(/^(#[0-9a-f]{3,8})\s+/i);a&&Zr.test(a[1])&&(r=a[1],t=t.replace(a[0]," ").trim());let s="",i=t.match(/^([^:]{1,80}?)\s*:\s+(.+)$/);if(i&&!/^(?:geo|https?)$/i.test(i[1])&&(s=i[1].trim(),t=i[2].trim()),Ki.test(t)){let b=t.split(Ki).filter(Boolean).map(m=>at(m,e));return b.length<2||b.some(m=>!m)?null:{kind:"route",label:s,color:r,stops:b,text:n}}let o=t.match(/^(.+?)\s*(?:=\s*)?([+-]?\d+(?:[.,]\d+)?)\s*(%)?$/),c=Ze(t,e)??(o?Ze(o[1],e):null);if(c&&!cn(t)){let b=c===Ze(t,e)||!o?null:Number(o[2].replace(",","."));return{kind:"country",code:c,label:s,color:r,value:b,text:n}}let u=t.match(/^([+-]?\d{1,3}(?:\.\d+)?)\s*[,; ]\s*([+-]?\d{1,3}(?:\.\d+)?)\s+([^\d\s°'"′″].*)$/u);if(u&&!s){let b=cn(`${u[1]}, ${u[2]}`);if(b)return Ft(u[3].trim(),r,{...b,source:"coords"},n)}if(!s&&!cn(t)){let b=t.split(/\s+/);for(let m=b.length-1;m>=2;m--){let _=cn(b.slice(0,m).join(" "));if(_)return Ft(b.slice(m).join(" "),r,{..._,source:"coords"},n)}}let h=at(t,e);return h?Ft(s,r,h,n):null}function Ft(n,e,t,r){return{kind:"marker",label:n,color:e,place:t,text:r}}function at(n,e="en"){let t=n.trim();if(!t)return null;let r=cn(t);if(r)return{...r,source:"coords"};let a=qi(t);if(a)return{lat:a.lat,lon:a.lon,source:"city",name:a.name};let s=Ze(t,e);return s?{country:s}:/\p{L}/u.test(t)&&t.length<=300?{address:t}:null}function cn(n){let e=n.trim();if(!e||e.length>200)return null;let t=e.match(/^geo:([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)/i)??e.match(/@([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)/)??e.match(/[?&](?:q|ll|query)=([+-]?\d+(?:\.\d+)?)(?:,|%2C)\s*([+-]?\d+(?:\.\d+)?)/i)??e.match(/[#&]map=\d+(?:\.\d+)?\/([+-]?\d+(?:\.\d+)?)\/([+-]?\d+(?:\.\d+)?)/);if(t)return xt(Number(t[1]),Number(t[2]));let r=e.match(/[?&]mlat=([+-]?\d+(?:\.\d+)?)/),a=e.match(/[?&]mlon=([+-]?\d+(?:\.\d+)?)/);if(r&&a)return xt(Number(r[1]),Number(a[1]));if(!/^[\s\d.,;:+\-°º'′’"″NSEWOnsewo]+$/.test(e)||!/\d/.test(e)||/[a-z]{2}/i.test(e))return null;let s=[],i={},o="",c=e.match(/[NSEWO]|[+-]?\d+(?:\.\d+)?\s*(?:°|º|''|["″]|['′’])?/gi)??[];for(let m of c){let _=m.trim();if(/^[NSEWO]$/i.test(_)){let S=_.toUpperCase()==="O"?"W":_.toUpperCase();i.deg!==void 0&&!i.hem&&!o?i.hem=S:(i.deg!==void 0&&s.push(i),i={},o=S);continue}let p=Number.parseFloat(_),g=_.replace(/^[+-]?\d+(?:\.\d+)?\s*/,"");/^(?:''|["″])$/.test(g)?i.sec=p:/^['′’]$/.test(g)?i.min=p:(i.deg!==void 0&&(s.push(i),i={}),i.deg=Math.abs(p),i.negative=p<0||Object.is(p,-0)||_.startsWith("-"),o&&(i.hem=o,o=""))}if(i.deg!==void 0&&s.push(i),s.length!==2)return null;let u=m=>{if((m.min??0)>=60||(m.sec??0)>=60)return NaN;let _=(m.deg??0)+(m.min??0)/60+(m.sec??0)/3600;return m.negative||m.hem==="S"||m.hem==="W"?-_:_},[h,b]=s;return(h.hem==="E"||h.hem==="W")&&(!b.hem||b.hem==="N"||b.hem==="S")&&([h,b]=[b,h]),h.hem==="E"||h.hem==="W"||b.hem==="N"||b.hem==="S"?null:xt(u(h),u(b))}function xt(n,e){return!Number.isFinite(n)||!Number.isFinite(e)||Math.abs(n)>90||Math.abs(e)>180?null:{lat:n,lon:e}}function Tu(n,e="en"){let t=[],r=[],a={},s=p=>typeof p=="string"||typeof p=="number"?String(p):"",i=p=>{let g=s(p?.color??p?.["marker-color"]??p?.stroke??p?.fill);return Zr.test(g)?g:""},o=p=>s(p?.label??p?.name??p?.title??p?.text).slice(0,200),c=p=>{if(typeof p=="string")return at(p,e);if(Array.isArray(p)&&p.length>=2)return Wi(xt(Number(p[1]),Number(p[0])));if(!p||typeof p!="object")return null;let g=p.lat??p.latitude,S=p.lon??p.lng??p.long??p.longitude;if(g!==void 0&&S!==void 0)return Wi(xt(Number(g),Number(S)));let M=s(p.address??p.place??p.city??p.query??p.coords);return M?at(M,e):null},u=p=>{let g=p?.type==="Feature"?p.geometry:p,S=p?.type==="Feature"?p.properties??{}:{};if(!g||typeof g.type!="string")return;let M=o(S),D=i(S);if(g.type==="Point"){let j=c(g.coordinates);j?t.push(Ft(M,D,j,M)):r.push(JSON.stringify(g.coordinates))}else if(g.type==="MultiPoint")for(let j of g.coordinates??[]){let P=c(j);P&&t.push(Ft(M,D,P,M))}else if(g.type==="GeometryCollection")for(let j of g.geometries??[])u({type:"Feature",properties:S,geometry:j});else/^(?:Multi)?(?:LineString|Polygon)$/.test(g.type)&&t.push({kind:"shape",label:M,color:D,geometry:g,text:M||g.type})};if(n?.type==="FeatureCollection"){for(let p of(n.features??[]).slice(0,Yr))u(p);return{items:t,invalid:r,view:a}}if(n?.type==="Feature"||/^(?:Multi)?(?:Point|LineString|Polygon)$|^GeometryCollection$/.test(n?.type??""))return u(n),{items:t,invalid:r,view:a};let h=Array.isArray(n)?n:n?.markers??n?.places??n?.points??[];for(let p of Array.isArray(h)?h.slice(0,Yr):[]){let g=c(p);g&&!("country"in g)?t.push(Ft(o(p),i(p),g,o(p)||JSON.stringify(p))):r.push(typeof p=="string"?p:JSON.stringify(p))}let b=n?.countries??n?.highlight,m=Array.isArray(b)?b.map(p=>typeof p=="string"?[p,null]:[s(p?.code??p?.id??p?.country??p?.name),p]):b&&typeof b=="object"?Object.entries(b):[];for(let[p,g]of m){let S=Ze(p,e);if(!S){r.push(p);continue}let M=typeof g=="number"?g:typeof g?.value=="number"?g.value:null,D=typeof g=="string"&&Zr.test(g)?g:i(g);t.push({kind:"country",code:S,label:o(g),color:D,value:M,text:p})}for(let p of Array.isArray(n?.routes)?n.routes:[]){let g=Array.isArray(p)?p:p?.stops??[p?.from,p?.to],S=(Array.isArray(g)?g:[]).map(c);S.length>=2&&S.every(Boolean)?t.push({kind:"route",label:o(p),color:i(p),stops:S,text:o(p)||"route"}):r.push(JSON.stringify(p))}for(let p of Array.isArray(n?.features)?n.features:[])u(p);let _=n?.center?c(n.center):null;return _&&"lat"in _&&(a.center={lat:_.lat,lon:_.lon}),typeof n?.zoom=="number"&&(a.zoom=n.zoom),{items:t,invalid:r,view:a}}function Wi(n){return n?{...n,source:"coords"}:null}function ge(n,e,t="decimal"){if(t==="decimal")return`${n.toFixed(5)}, ${e.toFixed(5)}`;let r=(a,s,i)=>{let o=Math.abs(a),c=Math.floor(o),u=Math.floor((o-c)*60),h=Math.round(((o-c)*60-u)*600)/10;return h>=60&&([h,u]=[0,u+1]),u>=60&&([u,c]=[0,c+1]),`${c}\xB0${String(u).padStart(2,"0")}\u2032${h.toFixed(1).padStart(4,"0")}\u2033${a<0?i:s}`};return`${r(n,"N","S")} ${r(e,"E","W")}`}function Yi(n,e){let t=Math.PI/180,r=(e.lat-n.lat)*t,a=(e.lon-n.lon)*t,s=Math.sin(r/2)**2+Math.cos(n.lat*t)*Math.cos(e.lat*t)*Math.sin(a/2)**2;return 2*6371.0088*Math.asin(Math.min(1,Math.sqrt(s)))}function Zi(n){let e=Array.isArray(n)?n[0]:n?.features?.[0]??n?.results?.[0]??n;if(!e||typeof e!="object")return null;let t=String(e.display_name??e.properties?.label??e.properties?.display_name??e.properties?.name??e.formatted_address??e.name??""),r=e.geometry?.coordinates;if(Array.isArray(r)){let i=xt(Number(r[1]),Number(r[0]));return i?{...i,name:t}:null}let a=e.geometry?.location??e,s=xt(Number(a.lat??a.latitude),Number(a.lon??a.lng??a.longitude));return s?{...s,name:t}:null}function Ji(n,e,t="en"){let r=encodeURIComponent(e),s={nominatim:`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&accept-language=${encodeURIComponent(t)}&q={q}`,photon:"https://photon.komoot.io/api/?limit=1&q={q}",ban:"https://api-adresse.data.gouv.fr/search/?limit=1&q={q}"}[n.trim().toLowerCase()]??n.trim();return!/^https?:\/\//i.test(s)||!s.includes("{q}")?null:s.replaceAll("{q}",r)}var Hn=null;function Xr(){if(Hn)return Hn;let n=W().vendorUrl||An(),e={ready:!1,geo:null,promise:Promise.resolve()};return e.promise=import(new URL("geo.js",n||location.href).href).then(t=>(e.geo=t,e.ready=!0,t),t=>{throw Hn=null,t}),Hn=e,e}En({en:ji,fr:Fi});var ku="http://www.w3.org/2000/svg",Ve=960,Ee=540,Qr=60,Nu=25,Xi=["natural-earth","equal-earth","mercator","equirectangular","globe","azimuthal-equal-area","azimuthal-equidistant","stereographic","gnomonic","transverse-mercator","conic-equal-area","conic-conformal"],Je=new Set(["globe","azimuthal-equal-area","azimuthal-equidistant","stereographic","gnomonic"]),ea={globe:90,stereographic:120,gnomonic:60,"azimuthal-equal-area":179.9,"azimuthal-equidistant":179.9},Qi=["light","dark","political","satellite","night","blueprint","vintage","mono"],eo=new WeakMap,un=new Map;function H(n,e={}){let t=document.createElementNS(ku,n);for(let[r,a]of Object.entries(e))a!==null&&t.setAttribute(r,String(a));return t}var ta=class extends $e{static type="map";static componentAttributes=Object.freeze(["projection","basemap","center","zoom","highlight","geocoder","graticule","labels","controls","list","pick","scroll-zoom","coords-format","height","movie"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,download:!0,fullscreen:!0,controls:!0,list:!0}};static styles=[Da];static allowEmpty=!0;static upgradeProperties=["content"];constructor(){super(),this.viewState=null,this.projectionState=null,this.basemapState=null,this.graticuleState=null,this.selected=null,this.pins=[],this.projection=null,this.path=null,this.svgEl=null,this.stage=null,this.tooltip=null,this.readout=null,this.statusLine=null,this.countryEls=[],this.updaters=[],this.frameRequest=0,this.flight=0,this.editor=null,this.previewTimer=void 0,this.geocoding=null,this.movie=null,this.changeTimer=void 0}disconnectedCallback(){cancelAnimationFrame(this.frameRequest),cancelAnimationFrame(this.flight),this.movie?.abort(),clearTimeout(this.previewTimer),clearTimeout(this.changeTimer),this.geocoding?.abort(),this.editor?.destroy(),super.disconnectedCallback()}flag(e,t){return Ie(this.getAttribute(e))??t}input(){let e=Jr(this.text??"",this.locale);for(let t of(this.getAttribute("highlight")??"").split(/[\s,;]+/).filter(Boolean)){let r=Ze(t,this.locale);r&&!e.items.some(a=>a.kind==="country"&&a.code.a3===r.a3)&&e.items.push({kind:"country",code:r,label:"",color:"",value:null,text:t})}return e}get projectionName(){let e=(this.projectionState??this.getAttribute("projection")??"").toLowerCase(),r={orthographic:"globe","3d":"globe",flat:"natural-earth","plate-carree":"equirectangular",azimuthal:"azimuthal-equidistant"}[e]??e;return Xi.includes(r)?r:"natural-earth"}get basemap(){let e=(this.basemapState??this.getAttribute("basemap")??"").toLowerCase(),r={sky:"satellite",terrain:"satellite",earth:"satellite",space:"night"}[e]??e;return Qi.includes(r)?r:"light"}initialView(){let e=Jr(this.text??"",this.locale).view,t=this.getAttribute("center"),r=t?at(t,this.locale):null,a=e.center??null;r&&"lat"in r?a=r:r&&"country"in r&&(a=this.countryCenter(r.country));let s=Number(this.getAttribute("zoom")??e.zoom??1);return{lon:a?.lon??(this.projectionName==="globe"?10:0),lat:a?.lat??(Je.has(this.projectionName)?30:0),zoom:Number.isFinite(s)?Math.min(Qr,Math.max(1,s)):1}}get view(){let e=this.viewState??this.initialView();return{lat:e.lat,lon:e.lon,zoom:e.zoom,projection:this.projectionName,basemap:this.basemap}}get items(){return this.input().items.map(e=>{if(e.kind==="country")return{kind:"country",label:e.label||Me(e.code,this.locale),code:e.code.a2||e.code.a3,value:e.value};if(e.kind==="marker"){let t=this.locate(e.place);return{kind:"marker",label:this.markerLabel(e),lat:t?.lat,lon:t?.lon}}return{kind:e.kind,label:e.label}})}locate(e){if("lat"in e)return e;if("country"in e)return this.countryCenter(e.country);let t=un.get(e.address.toLowerCase());return t&&t!=="none"&&t!=="pending"?t:null}markerLabel(e){let t=e.place;return e.label?e.label:"name"in t&&t.name?t.name:"address"in t?t.address:"country"in t?Me(t.country,this.locale):ge(t.lat,t.lon,this.coordsFormat)}get coordsFormat(){return this.getAttribute("coords-format")==="dms"?"dms":"decimal"}renderContent(e){let t=this.t,{items:r,invalid:a}=this.input(),s=f("div",{class:"body map-body",part:"body"});this.feature("controls")&&s.append(this.controlsView()),this.stage=f("div",{class:"map-stage",part:"stage",attrs:{"data-basemap":this.basemap}});let i=this.getAttribute("height");i&&/^[\d.]+(?:px|em|rem|vh|%)$/.test(i)&&(this.stage.style.height=i),s.append(this.stage),this.statusLine=f("p",{class:"map-status",attrs:{role:"status"}}),s.append(this.statusLine);let o=f("div",{class:"map-legend-host"});s.append(o),this.feature("list")&&s.append(f("div",{class:"map-list-host"})),a.length&&s.append(f("p",{class:"map-muted",text:t("mapInvalidLines",{list:a.slice(0,5).join(" \xB7 ")})}));let c=f("div",{class:"panel"}),u=[];if(this.editing){let _=this.createEditor();c.classList.add("map-edit"),c.append(f("div",{class:"body editor-body",part:"body editor"},_.element),s),u=this.historyButtons(_)}else c.append(s);let h=[...u,this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.geoJson(),this.downloadName("map.geojson"),"application/geo+json"):null,this.feature("copy")?this.copyButton(()=>this.report(),t("mapCopyPlaces")):null],b=r.filter(_=>_.kind==="marker").length,m=b?`${t(`mapProjection_${this.projectionName}`)} \xB7 ${t("mapPlaces",{count:b})}`:t(`mapProjection_${this.projectionName}`);e.append(...this.chrome({badge:m,actions:h}),c),this.editor?.align(),this.draw()}controlsView(){let e=this.t,t=(i,o,c,u,h,b)=>{let m=_e(i),_=f("select",{class:"map-select",attrs:{id:m,"data-focus-key":i},on:{change:()=>b(_.value)}},...o.map(p=>f("option",{text:h(p),attrs:{value:p,selected:p===c}})));return f("div",{class:"map-control"},f("label",{attrs:{for:m},text:e(u)}),_)},r=_e("place"),a=f("input",{class:"map-search-input",attrs:{id:r,type:"search",autocomplete:"off",spellcheck:"false",placeholder:e("mapSearchPlaceholder"),"data-focus-key":"place"}}),s=f("form",{class:"map-search",attrs:{role:"search"},on:{submit:i=>{i.preventDefault(),this.find(a.value)}}},f("label",{class:"sr-only",attrs:{for:r},text:e("mapSearch")}),a,f("button",{class:"btn map-go",attrs:{type:"submit","aria-label":e("mapSearch"),title:e("mapSearch")}},Pe("search")));return f("div",{class:"map-controls",part:"controls"},s,t("projection",Xi,this.projectionName,"mapProjection",i=>e(`mapProjection_${i}`),i=>{let o=Je.has(this.projectionName);this.projectionState=i,this.viewState&&o!==Je.has(i)&&(this.viewState.zoom=1),this.redrawAll(),this.changed()}),t("basemap",Qi,this.basemap,"mapBasemap",i=>e(`mapBasemap_${i}`),i=>{this.basemapState=i,this.redrawAll(),this.changed()}),f("label",{class:"map-check"},f("input",{attrs:{type:"checkbox",checked:this.showGraticule,"data-focus-key":"graticule"},on:{change:i=>{this.graticuleState=i.target.checked,this.redrawAll()}}}),f("span",{text:e("mapGraticule")})))}get showGraticule(){return this.graticuleState??this.flag("graticule",!0)}redrawAll(){if(!this.stage)return;this.stage.dataset.basemap=this.basemap,this.draw();let e=this.root.querySelector(".badge");e&&(e.textContent=e.textContent?.replace(/^[^·]+/,`${this.t(`mapProjection_${this.projectionName}`)} `).trim()??"")}draw(){let e=this.stage;if(!e)return;let t=Xr();if(!t.ready){e.replaceChildren(Pt(this.t)),t.promise.then(()=>{this.stage===e&&(this.draw(),this.renderSide())},r=>{this.stage===e&&e.replaceChildren(Fe(this.t("mapLoadFailed",{message:String(r?.message??r)})))});return}this.build(t.geo),this.renderSide(),this.geocodeItems()}get geo(){return Xr().geo}build(e){let t=this.t,r=this.stage,{items:a}=this.input(),s=this.projectionName,i={glow:_e("glow"),shade:_e("shade"),clip:_e("clip"),ocean:_e("ocean")};this.updaters=[],this.countryEls=[];let o=H("svg",{viewBox:`0 0 ${Ve} ${Ee}`,class:"map-svg",part:"map",role:"application","aria-roledescription":t("mapRole"),tabindex:"0",preserveAspectRatio:"xMidYMid meet"});o.setAttribute("aria-label",this.summary(a));let c=_e("help");o.setAttribute("aria-describedby",c),this.svgEl=o;let u=H("defs"),h=H("radialGradient",{id:i.ocean,cx:"50%",cy:"45%",r:"60%"});h.append(H("stop",{offset:"0%",class:"ocean-a"}),H("stop",{offset:"100%",class:"ocean-b"}));let b=H("radialGradient",{id:i.shade,cx:"35%",cy:"30%",r:"75%"});b.append(H("stop",{offset:"0%",class:"shade-a"}),H("stop",{offset:"65%",class:"shade-b"}),H("stop",{offset:"100%",class:"shade-c"}));let m=H("filter",{id:i.glow,x:"-20%",y:"-20%",width:"140%",height:"140%"});m.append(H("feGaussianBlur",{stdDeviation:"12"}));let _=H("clipPath",{id:i.clip}),p=H("path");_.append(p),u.append(h,b,m,_),o.append(u);let g=Je.has(s);if(g&&(this.basemap==="night"||this.basemap==="satellite")){let E=H("g",{class:"map-stars","aria-hidden":"true"}),L=7,z=()=>(L=L*16807%2147483647)/2147483647;for(let Y=0;Y<140;Y++)E.append(H("circle",{cx:(z()*Ve).toFixed(1),cy:(z()*Ee).toFixed(1),r:(z()*1.2+.2).toFixed(2),opacity:(z()*.7+.3).toFixed(2)}));o.append(E)}let S=H("path",{class:"map-atmosphere",filter:`url(#${i.glow})`}),M=H("path",{class:"map-sphere",fill:`url(#${i.ocean})`}),D=H("path",{class:"map-graticule"}),j=H("g",{class:"map-countries","clip-path":`url(#${i.clip})`}),P=H("path",{class:"map-borders"}),q=H("g",{class:"map-overlay","clip-path":`url(#${i.clip})`}),X=H("path",{class:"map-shading",fill:`url(#${i.shade})`}),ae=H("g",{class:"map-pins"}),ie=H("g",{class:"map-labels","aria-hidden":"true"});g&&o.append(S),o.append(M),this.showGraticule&&o.append(D),o.append(j,P,q),s==="globe"&&o.append(X),o.append(ae,ie);let Le=new Map(a.filter(E=>E.kind==="country").map(E=>[E.code.a3,E])),ke=[...Le.values()].map(E=>E.value).filter(E=>E!==null),se=Math.min(...ke),ye=Math.max(...ke);for(let[E,L]of e.countries.entries()){let z=$n(L.id,L.properties?.name),Y=Me(z,this.locale,L.properties?.name),B=Le.get(z.a3),Q=H("path",{class:`map-country c${E%8}${this.basemap==="satellite"?` ${Cu(e,L,z)}`:""}`,"data-code":z.a2||z.a3});if(B){if(Q.classList.add("highlighted"),B.color)Q.style.setProperty("fill",B.color);else if(B.value!==null&&ke.length){let K=ye===se?100:Math.round((B.value-se)/(ye-se)*100);Q.style.setProperty("fill",`color-mix(in oklab, var(--map-high) ${K}%, var(--map-low))`)}}this.selected===z.a3&&Q.classList.add("selected"),j.append(Q),this.countryEls.push({el:Q,feature:L,code:z,name:Y})}let Be=this.flag("labels",!0),Ne=E=>!g||e.geoDistance?.([E.lon,E.lat],[-this.projection.rotate()[0],-this.projection.rotate()[1]])<(ea[s]??90)*Math.PI/180;for(let E of a){if(E.kind==="shape"){let L=H("path",{class:`map-shape ${/Polygon/.test(E.geometry.type)?"area":"line"}`});E.color&&L.style.setProperty("--map-item",E.color),L.append(this.titleEl(E.label||t("mapShape"))),q.append(L),this.updaters.push(()=>L.setAttribute("d",this.path(E.geometry)??""))}if(E.kind==="route"){let L=H("path",{class:"map-route"});E.color&&L.style.setProperty("--map-item",E.color),q.append(L),this.updaters.push(()=>{let z=E.stops.map(B=>this.locate(B));if(z.some(B=>!B))return L.removeAttribute("d");let Y={type:"LineString",coordinates:z.map(B=>[B.lon,B.lat])};L.setAttribute("d",this.path(Y)??"")})}}let Re=[...a.flatMap(E=>E.kind==="marker"?[{place:E.place,label:this.markerLabel(E),color:E.color,dropped:!1}]:[]),...this.pins.map(E=>({place:{lat:E.lat,lon:E.lon,source:"coords"},label:E.label,color:"",dropped:!0}))];for(let E of Re){let L=H("g",{class:`map-pin${E.dropped?" dropped":""}`});E.color&&L.style.setProperty("--map-item",E.color),L.append(H("path",{d:"M0 0C-2-6-8-9-8-15a8 8 0 1 1 16 0c0 6-6 9-8 15Z",class:"map-pin-shape"}),H("circle",{cx:"0",cy:"-15",r:"3",class:"map-pin-dot"}),this.titleEl(E.label)),ae.append(L);let z=Be?H("text",{class:"map-label",dx:"10",dy:"-12"}):null;z&&(z.textContent=E.label,ie.append(z)),L.addEventListener("click",Y=>{Y.stopPropagation();let B=this.locate(E.place);B&&this.selectPoint(B,E.label)}),this.updaters.push(()=>{let Y=this.locate(E.place),B=Y&&Ne(Y)?this.projection([Y.lon,Y.lat]):null,Q=B&&B[0]>-20&&B[0]<Ve+20&&B[1]>-20&&B[1]<Ee+40;L.toggleAttribute("hidden",!Q),Q&&L.setAttribute("transform",`translate(${B[0].toFixed(1)} ${B[1].toFixed(1)})`),z&&(z.toggleAttribute("hidden",!Q),Q&&(z.setAttribute("x",B[0].toFixed(1)),z.setAttribute("y",B[1].toFixed(1))))})}if(Be)for(let E of Le.values()){let L=this.countryCenter(E.code);if(!L)continue;let z=H("text",{class:"map-country-label","text-anchor":"middle"});z.textContent=E.label||Me(E.code,this.locale)+(E.value!==null?` \xB7 ${this.number(E.value)}`:""),ie.append(z),this.updaters.push(()=>{let Y=Ne(L)?this.projection([L.lon,L.lat]):null;z.toggleAttribute("hidden",!Y),Y&&(z.setAttribute("x",Y[0].toFixed(1)),z.setAttribute("y",Y[1].toFixed(1)))})}this.updaters.unshift(()=>{let E=this.path({type:"Sphere"})??"";M.setAttribute("d",E),S.setAttribute("d",E),X.setAttribute("d",E),p.setAttribute("d",E),this.showGraticule&&D.setAttribute("d",this.path(e.geoGraticule10())??"");for(let L of this.countryEls)L.el.setAttribute("d",this.path(L.feature)??"");P.setAttribute("d",this.path(e.borders)??"")});let w=f("div",{class:"map-tooltip",part:"tooltip",attrs:{hidden:""}}),k=f("div",{class:"map-readout",attrs:{"aria-hidden":"true"}}),R=f("div",{class:"map-zoom"},de({icon:"plus",label:t("mapZoomIn"),key:"zoom-in",onClick:()=>this.zoomBy(2)}),de({icon:"minus",label:t("mapZoomOut"),key:"zoom-out",onClick:()=>this.zoomBy(.5)}),de({icon:"refresh",label:t("mapReset"),key:"reset",onClick:()=>this.reset()}),this.hasAttribute("movie")?this.trackButton():null),F=f("p",{class:"sr-only",attrs:{id:c},text:t("mapKeyboardHelp")});this.tooltip=w,this.readout=k,r.replaceChildren(o,R,w,k,F),r.classList.toggle("globe",g),this.bindPointer(o),this.update()}titleEl(e){let t=H("title");return t.textContent=e,t}summary(e){let t=this.t,r=a=>e.filter(s=>s.kind===a).length;return t("mapSummary",{projection:t(`mapProjection_${this.projectionName}`),places:r("marker")+this.pins.length,countries:r("country"),routes:r("route")})}update(){let e=this.geo;if(!e||!this.svgEl)return;let t=this.projectionName,r=this.viewState??this.initialView(),a=e.projections[t](),s=Je.has(t);s?a.rotate([-r.lon,-r.lat]).clipAngle(ea[t]??90):a.rotate([-r.lon,0]),a.precision(.4);let i=12;if(t==="mercator"||t==="transverse-mercator"?a.fitExtent([[i,i],[Ve-i,Ee-i]],{type:"Feature",geometry:{type:"MultiPoint",coordinates:[[r.lon-179.9,-80],[r.lon+179.9,84]]}}):a.fitExtent([[i,i],[Ve-i,Ee-i]],{type:"Sphere"}),a.scale(a.scale()*r.zoom),s)a.translate([Ve/2,Ee/2]);else{a.translate([Ve/2,Ee/2]);let o=a([r.lon,r.lat]),c=a.translate();a.translate([c[0]+Ve/2-o[0],c[1]+Ee/2-o[1]]);let u=e.geoPath(a),[[,h],[,b]]=u.bounds({type:"Sphere"}),m=Number.isFinite(h)?h:-1/0,_=Number.isFinite(b)?b:1/0,p=0;_-m<=Ee?p=Ee/2-(m+_)/2:m>0?p=-m:_<Ee&&(p=Ee-_);let g=a.translate();a.translate([g[0],g[1]+p])}this.projection=a,this.path=e.geoPath(a);for(let o of this.updaters)o()}scheduleUpdate(){this.frameRequest||(this.frameRequest=requestAnimationFrame(()=>{this.frameRequest=0,this.update()}))}unitsPerPixel(){let e=this.svgEl?.getBoundingClientRect();return!e||!e.width?1:Math.max(Ve/e.width,Ee/e.height)}pointOf(e){let t=this.svgEl.getBoundingClientRect(),r=this.unitsPerPixel();return[Ve/2+(e.clientX-t.left-t.width/2)*r,Ee/2+(e.clientY-t.top-t.height/2)*r]}pan(e,t){let r=this.viewState??=this.initialView(),a=this.projection?.scale()??150,s=180/Math.PI/a;r.lon=Xe(r.lon-e*s);let i=Je.has(this.projectionName)?90:85;r.lat=Math.max(-i,Math.min(i,r.lat+t*s)),this.scheduleUpdate()}zoomBy(e,t){let r=this.viewState??=this.initialView(),a=Math.min(Qr,Math.max(1,r.zoom*e));if(a!==r.zoom){if(t&&this.projection){let s=this.projection.invert?.(t);if(s&&Number.isFinite(s[0])){let i=1-r.zoom/a;r.lon=Xe(r.lon+Xe(s[0]-r.lon)*i),r.lat=r.lat+(s[1]-r.lat)*i}}r.zoom=a,this.scheduleUpdate(),this.changedSoon()}}reset(){this.viewState=null,this.selected=null,this.pins=[],this.build(this.geo),this.renderSide(),this.changed()}bindPointer(e){let t=new Map,r=0,a=0;e.addEventListener("pointerdown",i=>{i.button===0&&(e.setPointerCapture?.(i.pointerId),t.set(i.pointerId,[i.clientX,i.clientY]),r=0,t.size===2&&(a=no(t)))}),e.addEventListener("pointermove",i=>{this.hover(i);let o=t.get(i.pointerId);if(!o)return;let c=this.unitsPerPixel();if(t.size===2){t.set(i.pointerId,[i.clientX,i.clientY]);let b=no(t);a&&this.zoomBy(b/a),a=b,r+=10;return}let u=i.clientX-o[0],h=i.clientY-o[1];r+=Math.abs(u)+Math.abs(h),t.set(i.pointerId,[i.clientX,i.clientY]),r>3&&(e.classList.add("dragging"),this.pan(u*c,h*c))});let s=i=>{t.has(i.pointerId)&&(t.delete(i.pointerId),e.classList.remove("dragging"),!t.size&&r>3&&this.changed(),i.type==="pointerup"&&r<=3&&!t.size&&this.clickAt(i))};e.addEventListener("pointerup",s),e.addEventListener("pointercancel",s),e.addEventListener("pointerleave",()=>{this.tooltip&&(this.tooltip.hidden=!0),this.readout&&(this.readout.textContent="")}),e.addEventListener("dblclick",i=>{i.preventDefault(),this.zoomBy(2,this.pointOf(i))}),e.addEventListener("wheel",i=>{this.flag("scroll-zoom",!0)&&(i.preventDefault(),this.zoomBy(Math.exp(-i.deltaY*(i.deltaMode===1?.05:.0018)),this.pointOf(i)))},{passive:!1}),e.addEventListener("keydown",i=>{let u={ArrowLeft:()=>this.pan(-40,0),ArrowRight:()=>this.pan(40,0),ArrowUp:()=>this.pan(0,-40),ArrowDown:()=>this.pan(0,40),"+":()=>this.zoomBy(1.5),"=":()=>this.zoomBy(1.5),"-":()=>this.zoomBy(.6666666666666666),_:()=>this.zoomBy(.6666666666666666),0:()=>this.reset(),Home:()=>this.reset()}[i.key];!u||i.ctrlKey||i.metaKey||i.altKey||(i.preventDefault(),u(),i.key.startsWith("Arrow")&&this.changedSoon())})}countryOf(e){return this.countryEls.find(t=>t.el===e)??null}countryAt(e){let t=this.projection?.invert?.(e);if(!t||!Number.isFinite(t[0]))return null;let r=this.geo;return this.countryEls.find(a=>r.geoContains(a.feature,t))??null}hover(e){if(!this.projection||!this.tooltip||!this.readout)return;let t=this.pointOf(e),r=this.projection.invert?.(t),a=r&&Number.isFinite(r[0])&&(!Je.has(this.projectionName)||this.geo.geoDistance([r[0],r[1]],[-this.projection.rotate()[0],-this.projection.rotate()[1]])<(ea[this.projectionName]??90)*Math.PI/180);this.readout.textContent=a?ge(r[1],Xe(r[0]),this.coordsFormat):"";let s=a?this.countryOf(e.target):null;for(let u of this.countryEls)u.el.classList.toggle("hover",u===s);if(!s||e.buttons){this.tooltip.hidden=!0;return}let i=this.input().items.find(u=>u.kind==="country"&&u.code.a3===s.code.a3),o=i&&i.kind==="country"&&i.value!==null?` \xB7 ${this.number(i.value)}`:"";this.tooltip.textContent=`${Wr(s.code.a2)} ${s.name}${o}`.trim();let c=this.stage.getBoundingClientRect();this.tooltip.style.left=`${e.clientX-c.left+14}px`,this.tooltip.style.top=`${e.clientY-c.top+14}px`,this.tooltip.hidden=!1}clickAt(e){let t=this.pointOf(e),r=this.projection?.invert?.(t);if(!r||!Number.isFinite(r[0]))return;if(this.flag("pick",!1)){let s=to(r[1]),i=to(Xe(r[0]));this.pins=[{lat:s,lon:i,label:ge(s,i,this.coordsFormat)}],this.build(this.geo),this.renderSide(),this.selectPoint({lat:s,lon:i},ge(s,i,this.coordsFormat));return}let a=this.countryOf(e.target)??this.countryAt(t);a&&this.selectCountry(a.code,!1)}selectPoint(e,t){this.announce(this.t("mapSelectedPoint",{label:t,coords:ge(e.lat,e.lon,this.coordsFormat)})),ne(this,te.SELECT,{type:"point",label:t,lat:e.lat,lon:e.lon})}selectCountry(e,t){this.selected=this.selected===e.a3&&!t?null:e.a3;for(let o of this.countryEls)o.el.classList.toggle("selected",o.code.a3===this.selected);let r=Me(e,this.locale),a=this.input().items.find(o=>o.kind==="country"&&o.code.a3===e.a3),s=a&&a.kind==="country"?a.value:null,i=this.countryCenter(e);t&&i&&this.flyTo(i,this.countryZoom(e)),this.selected&&(this.announce(this.t("mapSelectedCountry",{name:r})),ne(this,te.SELECT,{type:"country",label:r,code:e.a2||e.a3,a3:e.a3,value:s,lat:i?.lat,lon:i?.lon}))}mainland(e){let t=this.geo,r=t?.countries.find(i=>$n(i.id,i.properties?.name).a3===e.a3);if(!r)return null;if(r.geometry.type!=="MultiPolygon")return r;let a=null,s=-1;for(let i of r.geometry.coordinates){let o={type:"Polygon",coordinates:i},c=t.geoArea(o);c>s&&([a,s]=[o,c])}return a}countryCenter(e){if(!this.geo)return null;let t=this.mainland(e);if(!t)return null;let[r,a]=this.geo.geoCentroid(t);return{lat:a,lon:r}}countryZoom(e){let t=this.mainland(e);if(!t)return 3;let r=this.geo.geoArea(t);return Math.min(14,Math.max(1.5,.9/Math.sqrt(r/(4*Math.PI))/4))}flyTo(e,t){let r={...this.viewState??this.initialView()},a={lon:e.lon,lat:Math.max(-85,Math.min(85,e.lat)),zoom:Math.min(Qr,Math.max(1,t))};if(cancelAnimationFrame(this.flight),typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches||!this.projection){this.viewState=a,this.update(),this.changed();return}let i=performance.now(),o=Xe(a.lon-r.lon),c=u=>{let h=Math.min(1,(u-i)/700),b=h<.5?4*h*h*h:1-(-2*h+2)**3/2;this.viewState={lon:Xe(r.lon+o*b),lat:r.lat+(a.lat-r.lat)*b,zoom:r.zoom*(a.zoom/r.zoom)**b},this.update(),h<1?this.flight=requestAnimationFrame(c):this.changed()};this.flight=requestAnimationFrame(c)}async find(e){let t=this.t,r=e.trim();if(!r||!this.geo)return;let a=r.match(/^(?:track|locate|traquer|localiser)\s+(.+)$/i);if(a){this.track(a[1]);return}let s=Ze(r,this.locale),i=s?{country:s}:at(r,this.locale);if(i&&"country"in i){this.selectCountry(i.country,!0),this.status(t("mapFoundCountry",{name:Me(i.country,this.locale)}));return}if(i&&"lat"in i){this.dropPin(i,i.name??ge(i.lat,i.lon,this.coordsFormat));return}if(i&&"address"in i){if(!this.getAttribute("geocoder")){this.status(t("mapNoGeocoder",{query:r}));return}this.status(t("mapGeocoding",{query:r}));let c=await this.geocode(r);c?this.dropPin(c,c.name||r):this.status(t("mapNotFound",{query:r}));return}this.status(t("mapNotFound",{query:r}))}trackButton(){let e=de({icon:"search",label:this.t("mapTrack"),key:"track",part:"track-button",onClick:()=>this.track(this.movieTarget())}),t=H("svg",{class:"icon",viewBox:"0 0 24 24",width:"16",height:"16",fill:"none",stroke:"currentColor","stroke-width":"2.1","stroke-linecap":"round","aria-hidden":"true"});return t.append(H("circle",{cx:"12",cy:"12",r:"10"}),H("path",{d:"M22 12h-4M6 12H2M12 6V2M12 22v-4"}),H("circle",{cx:"12",cy:"12",r:"1.5"})),e.replaceChildren(t),e}movieTarget(){let e=this.getAttribute("movie")?.trim();if(e&&!/^(?:true|on|yes|1)$/i.test(e))return e;let t=this.input().items.find(r=>r.kind==="marker");if(t&&t.kind==="marker"){let r=this.locate(t.place);if(r)return`${this.markerLabel(t)}: ${r.lat}, ${r.lon}`}return"0, 0"}async track(e){let t=this.t;if(!this.geo||!this.stage)return!1;let r=e.match(/^([^:]{1,80}?)\s*:\s+(.+)$/),a=at(r?r[2]:e,this.locale),s=null,i=(r?r[1]:e).trim();if(a&&"lat"in a)[s,i]=[a,r?i:a.name??i];else if(a&&"country"in a)[s,i]=[this.countryCenter(a.country),Me(a.country,this.locale)];else if(a&&"address"in a&&this.getAttribute("geocoder")){let g=await this.geocode(a.address);g&&(s=g)}if(!s)return this.status(t("mapNotFound",{query:i})),!1;let o=s;this.movie?.abort(),cancelAnimationFrame(this.flight);let c=new AbortController;this.movie=c;let{signal:u}=c;if(!Je.has(this.projectionName)){this.projectionState="globe",this.viewState={lon:o.lon-70,lat:10,zoom:1},this.pins=[],this.redrawAll();let g=this.root.querySelector('[data-focus-key="projection"]');g&&(g.value="globe")}let h=this.hudView();this.stage.append(h.root),this.stage.classList.add("movie");let b=()=>c.abort(),m=g=>g.key==="Escape"&&b();this.root.addEventListener("keydown",m),h.stop.addEventListener("click",b),this.announce(t("mapTracking",{label:i}));let _=typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches,p=g=>{let S=()=>(Math.random()-.5)*g;h.coords.textContent=ge(o.lat+S(),o.lon+S()*2,"dms")};try{if(_)this.viewState={lon:o.lon,lat:Math.max(-85,Math.min(85,o.lat)),zoom:32},this.update();else{let S=[["ESTABLISHING SATELLITE UPLINK",1,1800,60],["SIGNAL ACQUIRED \u2014 TRIANGULATING",2.5,1700,20],["CROSS-REFERENCING RELAY NODES",6,1600,5],["ENHANCE",14,1400,1],["ENHANCE",32,1300,.1]];for(let[M,D,j,P]of S)h.log(M),await this.animateView({lon:o.lon,lat:o.lat,zoom:D},j,u,q=>p(P*(1-q)+P*.15))}if(u.aborted)throw new Error("stopped");p(0),h.log("TARGET LOCATED"),h.root.classList.add("locked"),this.input().items.some(S=>{let M=S.kind==="marker"?this.locate(S.place):null;return M&&Math.abs(M.lat-o.lat)<1e-4&&Math.abs(M.lon-o.lon)<1e-4})||(this.pins=[{lat:o.lat,lon:o.lon,label:i}],this.build(this.geo),this.stage.append(h.root)),this.renderSide(),this.announce(t("mapTargetLocated",{label:i,coords:ge(o.lat,o.lon,this.coordsFormat)})),ne(this,te.SELECT,{type:"target",label:i,lat:o.lat,lon:o.lon}),this.changed(),await Mu(6e3,u)}catch{}finally{this.root.removeEventListener("keydown",m),h.root.remove(),this.stage?.classList.remove("movie"),this.movie===c&&(this.movie=null)}return!0}hudView(){let e=f("ol",{class:"hud-log",attrs:{"aria-hidden":"true"}}),t=f("div",{class:"hud-coords",attrs:{"aria-hidden":"true"}}),r=f("button",{class:"hud-stop",attrs:{type:"button"},text:this.t("mapStop")}),a=f("div",{class:"hud-time",attrs:{"aria-hidden":"true"}});return a.textContent=`${new Date().toISOString().slice(0,19).replace("T"," ")} UTC`,{root:f("div",{class:"map-hud",part:"hud"},f("div",{class:"hud-scan",attrs:{"aria-hidden":"true"}}),f("div",{class:"hud-corners",attrs:{"aria-hidden":"true"}}),f("div",{class:"hud-reticle",attrs:{"aria-hidden":"true"}},f("span",{class:"hud-ring"}),f("span",{class:"hud-box"})),f("div",{class:"hud-top",attrs:{"aria-hidden":"true"}},f("span",{class:"hud-rec",text:"REC"}),f("span",{text:"SAT-7 // ORBITAL FEED"}),a),e,t,f("div",{class:"hud-locked",attrs:{"aria-hidden":"true"}},f("strong",{text:"TARGET LOCATED"})),r),coords:t,stop:r,log:i=>{for(e.append(f("li",{text:`> ${i}`}));e.children.length>5;)e.firstElementChild?.remove()}}}animateView(e,t,r,a){let s={...this.viewState??this.initialView()},i=Xe(e.lon-s.lon),o=Math.max(-85,Math.min(85,e.lat));return new Promise(c=>{let u=performance.now(),h=b=>{if(r.aborted)return c();let m=Math.min(1,(b-u)/t),_=m<.5?4*m*m*m:1-(-2*m+2)**3/2;this.viewState={lon:Xe(s.lon+i*_),lat:s.lat+(o-s.lat)*_,zoom:s.zoom*(e.zoom/s.zoom)**_},this.update(),a?.(m),m<1?this.flight=requestAnimationFrame(h):c()};this.flight=requestAnimationFrame(h)})}dropPin(e,t){this.pins=[{lat:e.lat,lon:e.lon,label:t}];let r=this.viewState??this.initialView();this.build(this.geo),this.renderSide(),this.flyTo(e,Math.max(r.zoom,Je.has(this.projectionName)?2:4)),this.status(this.t("mapFound",{label:t,coords:ge(e.lat,e.lon,this.coordsFormat)})),this.selectPoint(e,t)}status(e){this.statusLine&&(this.statusLine.textContent=e)}async geocode(e,t){let r=e.toLowerCase(),a=un.get(r);if(a==="none")return null;if(a&&a!=="pending")return a;let s=Ji(this.getAttribute("geocoder")??"",e,this.locale);if(!s)return null;try{let i=await fetch(s,{credentials:"omit",headers:{Accept:"application/json"},signal:t});if(!i.ok)throw new Error(String(i.status));let o=Zi(await i.json());return un.set(r,o??"none"),o}catch(i){return i?.name!=="AbortError"&&un.delete(r),null}}async geocodeItems(){let e=this.getAttribute("geocoder"),t=this.input().items.flatMap(a=>a.kind==="marker"&&"address"in a.place?[a.place.address]:a.kind==="route"?a.stops.flatMap(s=>"address"in s?[s.address]:[]):[]).filter(a=>!un.has(a.toLowerCase())).slice(0,Nu);if(!e||!t.length)return;this.geocoding?.abort();let r=new AbortController;this.geocoding=r;for(let[a,s]of t.entries()){if(r.signal.aborted||(a&&await new Promise(i=>setTimeout(i,1e3)),await this.geocode(s,r.signal),r.signal.aborted))return;this.update(),this.renderSide()}}renderSide(){let e=this.t,{items:t}=this.input(),r=this.root.querySelector(".map-legend-host"),a=t.flatMap(o=>o.kind==="country"&&o.value!==null&&!o.color?[o.value]:[]);r&&(r.replaceChildren(),a.length&&r.append(f("div",{class:"map-legend",part:"legend",attrs:{role:"group","aria-label":e("mapLegend")}},f("span",{class:"map-legend-value",text:this.number(Math.min(...a))}),f("span",{class:"map-legend-bar",attrs:{"aria-hidden":"true"}}),f("span",{class:"map-legend-value",text:this.number(Math.max(...a))}))));let s=this.root.querySelector(".map-list-host");if(!s)return;s.replaceChildren();let i=[];for(let o of t)if(o.kind==="marker"){let c=this.locate(o.place),u=this.markerLabel(o),h="address"in o.place&&!c,b=c?ge(c.lat,c.lon,this.coordsFormat):this.getAttribute("geocoder")?e("mapLocating"):e("mapNeedsGeocoder");i.push(this.rowView("marker",u,b,o.color,c?()=>this.flyTo(c,Math.max((this.viewState??this.initialView()).zoom,4)):null,h))}else if(o.kind==="country"){let c=Me(o.code,this.locale),u=[o.code.a2||o.code.a3,o.value!==null?this.number(o.value):""].filter(Boolean).join(" \xB7 ");i.push(this.rowView("country",`${Wr(o.code.a2)} ${o.label||c}`.trim(),u,o.color,()=>this.selectCountry(o.code,!0),!1))}else if(o.kind==="route"){let c=o.stops.map(m=>this.locate(m)),u=o.stops.map(m=>"name"in m&&m.name?m.name:"address"in m?m.address:"country"in m?Me(m.country,this.locale):ge(m.lat,m.lon,this.coordsFormat)),h=0;for(let m=1;m<c.length;m++){let _=c[m-1],p=c[m];_&&p&&(h+=Yi(_,p))}let b=c[0];i.push(this.rowView("route",o.label||u.join(" \u2192 "),h?e("mapDistance",{km:this.number(Math.round(h))}):"",o.color,b?()=>this.flyTo(b,2):null,!1))}else o.kind==="shape"&&i.push(this.rowView("shape",o.label||e("mapShape"),o.geometry.type,o.color,null,!1));for(let o of this.pins)i.push(this.rowView("pin",o.label,ge(o.lat,o.lon,this.coordsFormat),"",()=>this.flyTo(o,Math.max((this.viewState??this.initialView()).zoom,4)),!1));i.length&&s.append(f("ul",{class:"map-list",part:"list",attrs:{"aria-label":e("mapList")}},...i))}rowView(e,t,r,a,s,i){let o=this.t,c=f("span",{class:`map-swatch ${e}`,attrs:{"aria-hidden":"true"}});a&&c.style.setProperty("--map-item",a);let u=f("span",{class:"sr-only",text:`${o(`mapKind_${e}`)}: `}),h=s?f("button",{class:"map-item-go",attrs:{type:"button",title:o("mapShow",{label:t})},on:{click:s}},u,t):f("span",{class:"map-item-name"},u,t);return f("li",{class:`map-item ${e}${i?" pending":""}`},c,h,r?f("span",{class:"map-item-note",text:r}):null)}number(e){return new Intl.NumberFormat(this.locale,{maximumFractionDigits:2}).format(e)}report(){let e=[];for(let t of this.input().items)if(t.kind==="marker"){let r=this.locate(t.place);e.push(`${this.markerLabel(t)}: ${r?ge(r.lat,r.lon):"?"}`)}else t.kind==="country"?e.push(`${Me(t.code,this.locale)} (${t.code.a2||t.code.a3})${t.value!==null?`: ${t.value}`:""}`):t.kind==="route"&&e.push(t.stops.map(r=>{let a=this.locate(r);return a?ge(a.lat,a.lon):"?"}).join(" -> "));for(let t of this.pins)e.push(`${t.label}: ${ge(t.lat,t.lon)}`);return e.join(`
`)}geoJson(){let e=[];for(let t of this.input().items){let r={name:t.kind==="marker"?this.markerLabel(t):t.label||void 0,color:t.color||void 0};if(t.kind==="marker"){let a=this.locate(t.place);a&&e.push({type:"Feature",properties:r,geometry:{type:"Point",coordinates:[a.lon,a.lat]}})}else if(t.kind==="route"){let a=t.stops.map(s=>this.locate(s));a.every(Boolean)&&e.push({type:"Feature",properties:r,geometry:{type:"LineString",coordinates:a.map(s=>[s.lon,s.lat])}})}else if(t.kind==="shape")e.push({type:"Feature",properties:r,geometry:t.geometry});else if(t.kind==="country"){let a=this.geo?.countries.find(s=>$n(s.id,s.properties?.name).a3===t.code.a3);e.push({type:"Feature",properties:{...r,name:Me(t.code,this.locale),code:t.code.a3,value:t.value??void 0},geometry:a?.geometry??null})}}for(let t of this.pins)e.push({type:"Feature",properties:{name:t.label},geometry:{type:"Point",coordinates:[t.lon,t.lat]}});return JSON.stringify({type:"FeatureCollection",features:e},null,2)}changed(){clearTimeout(this.changeTimer),ne(this,te.CHANGE,this.view)}changedSoon(){clearTimeout(this.changeTimer),this.changeTimer=setTimeout(()=>ne(this,te.CHANGE,this.view),300)}createEditor(){return this.editor?.destroy(),this.editor=new Ge({text:this.text??"",language:"plaintext",lineNumbers:!0,wrap:!0,highlightLimit:W().highlightLimit,label:this.heading||this.t("editor"),placeholder:this.getAttribute("placeholder")??void 0,onInput:e=>this.edited(e),onChange:e=>ne(this,te.CHANGE,{value:e}),history:this.editHistory??void 0}),this.editor}contentEdited(){clearTimeout(this.previewTimer),this.previewTimer=setTimeout(()=>this.render(),300)}};function Cu(n,e,t){if(t.a3==="ATA"||t.a3==="GRL")return"ice";if(new Set(["DZA","LBY","EGY","MRT","MLI","NER","TCD","SDN","ESH","SAU","YEM","OMN","ARE","QAT","KWT","IRQ","JOR","SYR","IRN","AFG","PAK","TKM","UZB","KAZ","MNG","NAM","BWA","AUS","DJI","SOM","SOL","ERI","ISR","PSE","TUN","MAR"]).has(t.a3))return"desert";let a=eo.get(e);a===void 0&&(a=n.geoCentroid(e)[1],eo.set(e,a));let s=Math.abs(a);return s>58?"tundra":s>35?"forest":s>20?"steppe":"tropic"}function Mu(n,e){return new Promise(t=>{let r=setTimeout(t,n);e.addEventListener("abort",()=>{clearTimeout(r),t()})})}function Xe(n){return((n+180)%360+360)%360-180}function to(n){return Math.round(n*1e5)/1e5}function no(n){let[e,t]=[...n.values()];return Math.hypot(e[0]-t[0],e[1]-t[1])||1}var $t=`/*
 * Code view: used by <vt-code>, the Markdown source tab and the JSON raw view.
 */
.code-view {
  position: relative;
}

.code {
  display: grid;
  width: max-content;
  min-width: 100%;
  margin: 0;
  padding: var(--_space-3) 0;
  color: var(--_code-fg);
  font-family: var(--_font-mono);
  font-size: var(--_font-size);
  font-variant-ligatures: var(--vt-font-ligatures, none);
  line-height: var(--_line-height);
  tab-size: var(--_tab-size);
}

.wrap .code {
  width: auto;
}

.line {
  display: flex;
  min-width: 0;
}

/* Long code: off-screen blocks of lines skip layout and paint. */
.chunk.revealed {
  content-visibility: visible;
}

.chunk {
  display: block;
  content-visibility: auto;
  contain-intrinsic-block-size: auto
    calc(var(--_chunk-lines) * var(--_font-size) * var(--_line-height));
}

/* A block whose lines are not built yet keeps the height they will take. */
.chunk[data-pending] {
  block-size: calc(var(--_chunk-lines) * var(--_font-size) * var(--_line-height));
}

.gutter {
  position: sticky;
  left: 0;
  z-index: 1;
  flex: none;
  min-width: calc(var(--_digits, 2) * 1ch + 2 * var(--_space-3));
  padding: 0 var(--_space-3);
  border-right: 1px solid color-mix(in srgb, var(--_code-gutter) 35%, transparent);
  background: var(--_code-bg-solid);
  color: var(--_code-gutter);
  font-size: var(--_font-size-small);
  line-height: calc(var(--_font-size) * var(--_line-height));
  font-variant-numeric: tabular-nums;
  text-align: right;
  user-select: none;
  -webkit-user-select: none;
}

.gutter::before {
  content: attr(data-n);
}

.sign {
  flex: none;
  width: 2ch;
  padding-left: var(--_space-2);
  color: var(--_fg-muted);
  user-select: none;
  -webkit-user-select: none;
}

.content {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0 var(--_space-4);
  white-space: pre;
}

.sign + .content {
  padding-left: var(--_space-1);
}

.wrap .content {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.line.highlighted {
  background: var(--_line-highlight);
}

.line.highlighted .gutter {
  box-shadow: inset 2px 0 0 var(--_accent);
  color: var(--_code-fg);
}

.line.added {
  background: var(--_diff-added);
}

.line.removed {
  background: var(--_diff-removed);
}

.line.added .sign::before {
  content: '+';
  color: var(--_success);
}

.line.removed .sign::before {
  content: '\\2212';
  color: var(--_danger);
}

.line.hunk .content {
  color: var(--_info);
}

/* Collapsible: show the first N lines, fade the rest. */
.collapsed .code {
  max-height: calc(
    (var(--_collapse-lines) + 0.6) * var(--_font-size) * var(--_line-height) + var(--_space-3)
  );
  overflow: hidden;
}

.collapsed .code-view::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  height: calc(0.9 * var(--_font-size) * var(--_line-height));
  background: linear-gradient(transparent, var(--_code-bg-solid));
  pointer-events: none;
}

.more {
  display: flex;
  justify-content: center;
  padding: var(--_space-2);
  border-top: 1px solid var(--_border);
  background: var(--_surface);
}

/* ---------- Editor: a transparent textarea laid over the highlighted code ---------- */

.editor {
  position: relative;
  width: max-content;
  min-width: 100%;
}

.editor.wrap {
  width: auto;
}

.editor-layer {
  pointer-events: none;
}

/* Bold or italic tokens can shift characters in some fonts: keep the layer regular. */
.editor-layer .code * {
  font-style: inherit !important;
  font-weight: inherit !important;
}

/* An empty last line still needs its height under the caret. */
.editor-layer .content:empty::before {
  content: '\\200b';
}

.editor-input {
  position: absolute;
  top: 0;
  left: var(--_editor-gutter, 0px);
  width: calc(100% - var(--_editor-gutter, 0px));
  height: 100%;
  margin: 0;
  padding: var(--_space-3) var(--_space-4);
  overflow: hidden;
  border: 0;
  outline: none;
  background: transparent;
  color: transparent;
  -webkit-text-fill-color: transparent;
  caret-color: var(--_code-fg);
  font-family: var(--_font-mono);
  font-size: var(--_font-size);
  font-variant-ligatures: var(--vt-font-ligatures, none);
  line-height: var(--_line-height);
  tab-size: var(--_tab-size);
  white-space: pre;
  overflow-wrap: normal;
  resize: none;
}

.editor.wrap .editor-input {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.editor-input::selection {
  background: color-mix(in srgb, var(--_accent) 32%, transparent);
}

.editor-input::placeholder {
  color: var(--_fg-muted);
  -webkit-text-fill-color: var(--_fg-muted);
  opacity: 1;
}

/* Long text: plain text while typing, highlighting after a pause. */
.editor.pending .editor-input {
  color: var(--_fg);
  -webkit-text-fill-color: var(--_fg);
}

.editor.pending .editor-layer .content {
  visibility: hidden;
}

.body:has(.editor-input:focus) {
  outline: 2px solid var(--_accent);
  outline-offset: -2px;
}

.edit-status {
  display: flex;
  align-items: center;
  gap: var(--_space-2);
  padding: var(--_space-2) var(--_space-3);
  border-top: 1px solid var(--_border);
  background: var(--_surface);
  font-family: var(--_font-ui);
  font-size: var(--_font-size-small);
}

.edit-status.ok {
  color: var(--_success);
}

.edit-status.bad {
  color: var(--_danger);
}

.edit-status .icon {
  width: 14px;
  height: 14px;
  flex: none;
}
`;var ro=`/*
 * Shared by the elements that show a preview of JSON: the body, the editor above it, and the
 * small pieces they have in common.
 */
.data-body {
  display: grid;
  gap: var(--_space-4);
  padding: var(--_space-4) var(--_space-5);
  background: var(--_surface);
  container-type: inline-size;
  overscroll-behavior: auto;
}

:host([max-height]) .data-body,
.vt[data-fullscreen] .data-body {
  overscroll-behavior: contain;
}

.data-edit > .editor-body {
  max-height: min(40vh, 320px);
  border-bottom: 1px solid var(--_border);
}

.data-none {
  margin: 0;
  color: var(--_fg-muted);
  font: 400 var(--_font-size-ui) / 1.5 var(--_font-ui);
}

.data-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--_space-1);
}

.data-chip {
  min-height: 28px;
  padding: 2px 10px;
  border: 1px solid var(--_border-strong);
  border-radius: var(--_radius-full);
  background: transparent;
  color: var(--_fg-muted);
  font: 500 var(--_font-size-small) / 1.4 var(--_font-ui);
  cursor: pointer;
}

.data-chip:hover {
  background: var(--_accent-soft);
  color: var(--_fg);
}

.data-chip[aria-pressed='true'] {
  border-color: var(--_accent);
  background: var(--_accent-soft);
  color: var(--_fg);
}

.data-chip:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 1px;
}

.data-input {
  width: 100%;
  min-height: 36px;
  padding: 0 var(--_space-3);
  border: 1px solid var(--_border-strong);
  border-radius: var(--_radius-sm);
  background: var(--_surface-sunken);
  color: var(--_fg);
  font: 400 var(--_font-size-ui) / 1.4 var(--_font-ui);
}

.data-input:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 1px;
}

@media (pointer: coarse) {
  .data-chip {
    min-height: 44px;
  }
}
`;var ao=`/*
 * Key figures: tiles with a value, a change and a small line. Text stays in text colors, and a
 * change carries an arrow and a word as well as its color.
 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(var(--_columns, auto-fit), minmax(min(100%, 180px), 1fr));
  gap: var(--_space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.stats-tile {
  display: flex;
  flex-direction: column;
  gap: var(--_space-1);
  min-width: 0;
  padding: var(--_space-3) var(--_space-4);
  border: 1px solid var(--_border);
  border-radius: var(--_radius-sm);
}

.stats-tile a {
  color: var(--_accent-fg);
}

.stats-label {
  color: var(--_fg-muted);
  font: 500 var(--_font-size-ui) / 1.4 var(--_font-ui);
  overflow-wrap: anywhere;
}

.stats-tile a .stats-label {
  color: inherit;
}

.stats-value {
  color: var(--_fg);
  font: 700 28px / 1.2 var(--_font-ui);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.stats-change {
  display: inline-flex;
  align-items: flex-start;
  gap: 2px;
  color: var(--_fg-muted);
  font: 500 var(--_font-size-small) / 1.4 var(--_font-ui);
}

.stats-change .icon {
  flex: none;
  width: 14px;
  height: 14px;
  margin-top: 1px;
}

.stats-change.good {
  color: var(--_success);
}

.stats-change.bad {
  color: var(--_danger);
}

.stats-note {
  margin: 0;
  color: var(--_fg-muted);
  font: 400 var(--_font-size-small) / 1.45 var(--_font-ui);
}

/* ---------- Small line ---------- */

.stats-history {
  display: grid;
  gap: 2px;
  margin-top: var(--_space-1);
}

.stats-trend {
  border-radius: 2px;
  touch-action: pan-y;
}

.stats-trend:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 2px;
}

.stats-svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.stats-line {
  fill: none;
  stroke: var(--_accent-fg);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.stats-marker {
  fill: var(--_accent-fg);
  stroke: var(--_surface);
  stroke-width: 2;
}

.stats-guide {
  display: none;
  stroke: var(--_border-strong);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.stats-trend.active .stats-guide {
  display: inline;
}

.stats-point {
  min-height: 1.4em;
  color: var(--_fg-muted);
  font: 400 var(--_font-size-small) / 1.4 var(--_font-ui);
  overflow-wrap: anywhere;
}
`;var Iu=200,Du=[["year",31536e3],["month",2592e3],["day",86400],["hour",3600],["minute",60],["second",1]],Gn=class extends $e{static editorLanguage="json";constructor(){super(),this.editor=null,this.previewTimer=void 0}get now(){let e=this.getAttribute("now")?.trim();if(e){let t=/^\d+$/.test(e)?Number(e)*1e3:Date.parse(e);if(Math.abs(t)<=864e13)return t}return Date.now()}flag(e){return Ie(this.getAttribute(e))!==!1}relativeTime(e){let t=Math.round((e-this.now)/1e3),[r,a]=Du.find(([,i])=>Math.abs(t)>=i)??["second",1],s=Math.round(t/a);try{return new Intl.RelativeTimeFormat(this.locale,{numeric:"auto"}).format(s,r)}catch{return`${s} ${r}`}}formatDate(e,t={dateStyle:"medium",timeStyle:"short"}){try{return new Intl.DateTimeFormat(this.locale,t).format(e)}catch{return new Date(e).toISOString()}}previewPanel(e,t){let r=f("div",{class:"panel",attrs:{id:t}});if(!this.editing)return r.append(e),{panel:r,history:[]};let a=this.createEditor();return r.classList.add("data-edit"),r.append(f("div",{class:"body editor-body",part:"body source"},a.element),e),{panel:r,history:this.historyButtons(a)}}frameWith(e,t,r,{file:a,download:s=!0,badge:i="JSON"}){let{panel:o,history:c}=this.previewPanel(t,r);e.append(...this.chrome({badge:i,actions:[...c,this.editToggleButton(),this.fullscreenButton(),s&&this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(a),"application/json"):null,this.feature("copy")?this.copyButton(()=>this.text??""):null]}),o),this.editor?.align()}dataNotice(e){return Fe(e.error==="json"?this.t("jsonInvalid",{message:e.message}):this.t("dataNoList",{keys:e.message}))}createEditor(){this.editor?.destroy();let e=this.constructor;return this.editor=new Ge({text:this.text??"",language:e.editorLanguage,lineNumbers:!1,wrap:!0,highlightLimit:W().highlightLimit,label:this.heading||this.t("editor"),placeholder:this.getAttribute("placeholder")??void 0,onInput:t=>this.edited(t),onChange:t=>ne(this,te.CHANGE,{value:t}),history:this.editHistory??void 0}),this.editor}contentEdited(){clearTimeout(this.previewTimer),this.previewTimer=setTimeout(()=>this.render(),Iu)}};var Pu=new Set(["number","compact","currency","percent","bytes","duration"]),zu=500;function Bu(n){if(!Array.isArray(n))return[];let e=[];for(let t of n.slice(0,zu)){let r=Dt(qe(t)?t.value??t.y:t);r!==null&&e.push({label:qe(t)?De(t.label??t.x,100):"",value:r})}return e}function Uu(n,e){let t=Dt(n.change??n.delta);if(t!==null)return t;let r=Dt(n.previous);return r===null||e===null||r===0?null:(e-r)/Math.abs(r)*100}function ju(n){let e=Dt(n.value),t=De(n.format,20).toLowerCase(),r=Dt(n.digits),a=De(n.good,10).toLowerCase();return{label:xr(n,["label","name","title"],200),value:e,display:e===null?De(n.value,100):"",format:Pu.has(t)?t:"number",unit:De(n.unit,40),currency:/^[A-Za-z]{3}$/.test(De(n.currency,3))?De(n.currency,3).toUpperCase():"USD",digits:r!==null&&r>=0&&r<=6?Math.floor(r):null,change:Uu(n,e),good:a==="down"||a==="none"?a:"up",against:xr(n,["against","period","compare"],100),description:De(n.description,500),url:Ja(n.url??n.href),series:Bu(n.series??n.history??n.trend??n.spark)}}function na(n){let e=Xa(n,["stats","items","metrics","kpis"]);return e.ok?{ok:!0,stats:e.items.map(ju).filter(t=>t.label||t.value!==null)}:e}function so(n,e){return n===0||e==="none"?"neutral":n>0==(e==="up")?"good":"bad"}function io(n,e,t,r){let a=n.map(o=>o.value),s=Math.min(...a),i=Math.max(...a)-s;return n.map((o,c)=>({x:n.length>1?r+c/(n.length-1)*(e-r*2):e/2,y:i?t-r-(o.value-s)/i*(t-r*2):t/2}))}var oo=Object.freeze({statsUp:"Up {change}",statsDown:"Down {change}",statsFlat:"No change",statsAgainst:"{change} {against}",statsHistory:"History of {name}",statsPoint:"Point {n}",statsEmpty:"No figures to show."}),lo=Object.freeze({statsUp:"En hausse de {change}",statsDown:"En baisse de {change}",statsFlat:"Sans changement",statsAgainst:"{change} {against}",statsHistory:"Historique de {name}",statsPoint:"Point {n}",statsEmpty:"Aucun chiffre \xE0 afficher."});En({en:oo,fr:lo});var Fu="http://www.w3.org/2000/svg",co=240,ra=48,$u=5;function Vn(n,e){let t=document.createElementNS(Fu,n);for(let[r,a]of Object.entries(e))t.setAttribute(r,String(a));return t}var aa=class extends Gn{static type="stats";static componentAttributes=Object.freeze(["columns","trend","changes"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,download:!0,fullscreen:!0}};static styles=[tt,$t,ro,ao];constructor(){super(),this.panelId=_e("panel")}get stats(){let e=na(this.text??"");return e.ok?e.stats:[]}renderContent(e){let t=na(this.text??""),r=f("div",{class:"body data-body stats-body",part:"body"});if(!t.ok)r.append(this.dataNotice(t));else if(!t.stats.length)r.append(f("p",{class:"data-none",text:this.t("statsEmpty")}));else{let a=f("ul",{class:"stats-grid"},...t.stats.map((i,o)=>this.statView(i,o))),s=Number(this.getAttribute("columns"));Number.isInteger(s)&&s>=1&&s<=12&&a.style.setProperty("--_columns",String(s)),r.append(a)}this.frameWith(e,r,this.panelId,{file:"stats.json"})}statView(e,t){let r=f("span",{class:"stats-label",part:"label",text:e.label});return f("li",{class:"stats-tile",part:"stat"},e.url?f("a",{attrs:{href:e.url,rel:"noopener noreferrer"}},r):r,f("span",{class:"stats-value",part:"value",text:this.valueText(e,e.value)}),e.change!==null&&this.flag("changes")?this.changeView(e):null,e.series.length>1&&this.flag("trend")?this.trendView(e,t):null,e.description?f("p",{class:"stats-note",text:e.description}):null)}valueText(e,t){let r=t===null?e.display:this.formatValue(e,t);return e.unit?`${r} ${e.unit}`:r}formatValue(e,t){let r=e.digits===null?{}:{minimumFractionDigits:e.digits,maximumFractionDigits:e.digits};try{switch(e.format){case"compact":return this.number(t,{notation:"compact",maximumFractionDigits:1,...r});case"currency":return this.number(t,{style:"currency",currency:e.currency,...r});case"percent":return this.number(t/100,{style:"percent",maximumFractionDigits:1,...r});case"bytes":return this.bytes(t);case"duration":return this.duration(t);default:return this.number(t,r)}}catch{return String(t)}}number(e,t){return new Intl.NumberFormat(this.locale,t).format(e)}bytes(e){let t=["byte","kilobyte","megabyte","gigabyte","terabyte","petabyte"],r=Math.abs(e),a=Math.min(t.length-1,r<1?0:Math.floor(Math.log(r)/Math.log(1e3)));return this.number(e/1e3**a,{style:"unit",unit:t[a],unitDisplay:"short",maximumFractionDigits:1})}duration(e){let t=[["day",86400],["hour",3600],["minute",60],["second",1]],[r,a]=t.find(([,s])=>Math.abs(e)>=s)??t[3];return this.number(e/a,{style:"unit",unit:r,unitDisplay:"short",maximumFractionDigits:1})}changeView(e){let t=this.t,r=e.change,a=so(r,e.good),s=this.number(Math.abs(r)/100,{style:"percent",maximumFractionDigits:1}),i=t("statsFlat");return r>0?i=t("statsUp",{change:s}):r<0&&(i=t("statsDown",{change:s})),f("span",{class:`stats-change ${a}`,part:"change"},r?Pe(r>0?"chevron-up":"chevron-down"):null,f("span",{text:e.against?t("statsAgainst",{change:i,against:e.against}):i}))}trendView(e,t){let r=this.t,{series:a}=e,s=io(a,co,ra,$u),i=g=>`${a[g].label||r("statsPoint",{n:g+1})}: ${this.valueText(e,a[g].value)}`,o=a.length-1,c=Vn("polyline",{class:"stats-line",points:s.map(g=>`${g.x.toFixed(1)},${g.y.toFixed(1)}`).join(" ")}),u=Vn("line",{class:"stats-guide",y1:0,y2:ra,x1:0,x2:0}),h=Vn("circle",{class:"stats-marker",r:4}),b=Vn("svg",{class:"stats-svg",viewBox:`0 0 ${co} ${ra}`,"aria-hidden":"true"});b.append(u,c,h);let m=f("span",{class:"stats-point"}),_=f("div",{class:"stats-trend",part:"trend",attrs:{role:"slider",tabindex:"0","data-focus-key":`trend-${t}`,"aria-label":r("statsHistory",{name:e.label}),"aria-valuemin":"0","aria-valuemax":String(a.length-1)}},b),p=(g,S=!0)=>{o=g,h.setAttribute("cx",String(s[g].x)),h.setAttribute("cy",String(s[g].y)),u.setAttribute("x1",String(s[g].x)),u.setAttribute("x2",String(s[g].x)),_.classList.toggle("active",S),_.setAttribute("aria-valuenow",String(g)),_.setAttribute("aria-valuetext",i(g)),m.textContent=S?i(g):"\xA0"};return p(o,!1),_.addEventListener("pointermove",g=>{let S=_.getBoundingClientRect(),M=S.width?(g.clientX-S.left)/S.width:1;p(Math.max(0,Math.min(a.length-1,Math.round(M*(a.length-1)))))}),_.addEventListener("pointerleave",()=>p(a.length-1,this.root.activeElement===_)),_.addEventListener("focus",()=>p(o)),_.addEventListener("blur",()=>p(a.length-1,!1)),_.addEventListener("keydown",g=>{let S=Hu(g.key,o,a.length);S!==null&&(g.preventDefault(),p(S))}),f("div",{class:"stats-history"},_,m)}};function Hu(n,e,t){return n==="ArrowLeft"||n==="ArrowDown"?Math.max(0,e-1):n==="ArrowRight"||n==="ArrowUp"?Math.min(t-1,e+1):n==="Home"?0:n==="End"?t-1:null}function uo(n){return es(n,{keys:["code","content","source","text"],attributes:{language:"language",lang:"language",label:"label",filename:"label",file:"label",title:"label",highlightLines:"highlight-lines",highlight:"highlight-lines",startLine:"start-line",lineNumbers:"line-numbers",wrap:"wrap",tabSize:"tab-size"},otherwise:e=>({content:Wt(e),attributes:{language:"json"}})})}var ho={bash:"sh",css:"css",diff:"diff",javascript:"js",json:"json",markdown:"md",plaintext:"txt",python:"py",shell:"sh",typescript:"ts",xml:"html",yaml:"yml"},ia=class extends $e{static type="code";static fromData=uo;static dataAttributes=Object.freeze(["language","label","highlight-lines","start-line","line-numbers","wrap","tab-size"]);static componentAttributes=Object.freeze(["language","line-numbers","start-line","highlight-lines","wrap","wrap-toggle","collapsible","diff","tab-size"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,search:!0,download:!0,"line-numbers":!0,"wrap-toggle":!0,fullscreen:!0}};static styles=[tt,$t];constructor(){super(),this.wrapState=null,this.expanded=!1,this.editor=null,this._detected=void 0}attributeChangedCallback(e,t,r){e==="wrap"&&(this.wrapState=null),e==="collapsible"&&(this.expanded=!1),super.attributeChangedCallback(e,t,r)}contentChanged(){this.expanded=!1,this._detected=void 0}language(){let e=this.getAttribute("language")?.trim().toLowerCase()||"",t=this.text??"";if(e==="auto")return this._detected??=t.length<=W().highlightLimit?Pi(t):"plaintext",{name:this._detected,label:sa(this._detected)};if(this.feature("diff")&&!e)return{name:"plaintext",label:"diff"};let r=Ii(e);return r?zn(r)?{name:r,label:sa(r)}:(Di(r).then(a=>a&&this.requestRender()),{name:"plaintext",label:sa(r)}):{name:"plaintext",label:e?e.slice(0,24):""}}get wrapped(){return this.wrapState??this.feature("wrap")}renderContent(e){let t=this.text??"",r=this.t,a=this.language();if(this.applyTabSize(e),this.editing){this.renderEditor(e,a);return}let s=Bn(t,{language:a.name,lineNumbers:this.feature("line-numbers"),startLine:Rt(this.getAttribute("start-line"),{min:-1e9,max:1e9,fallback:1}),highlightRanges:fr(this.getAttribute("highlight-lines")),diff:this.feature("diff"),highlightLimit:W().highlightLimit,diffLabels:{added:r("added"),removed:r("removed")}}),i=Rt(this.getAttribute("collapsible"),{min:1,max:1e5,fallback:0}),o=i>0&&s.lineCount>i+1&&!this.expanded,c=new Xt(s.code,{skip:".sign"}),u={run:m=>(m&&this.revealAll(e),c.run(m)),go:m=>Kr(c.go(m)),clear:()=>c.clear()},h=[this.searchButton(u),this.feature("wrap-toggle")?de({icon:"wrap",label:r("wrap"),key:"wrap",part:"wrap-button",pressed:this.wrapped,onClick:()=>{this.wrapState=!this.wrapped,this.render()}}):null,this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(`code.${ho[a.name]??"txt"}`),"text/plain"):null,this.feature("copy")?this.copyButton(()=>this.text??"",r("copyCode")):null],b=f("div",{class:"body",part:"body",attrs:{tabindex:"0",role:"region","aria-label":this.heading||`${r("code")}${a.label?` (${a.label})`:""}`}},s.element);if(e.classList.toggle("wrap",this.wrapped),e.classList.toggle("collapsed",o),o&&e.style.setProperty("--_collapse-lines",String(i)),e.append(...this.chrome({badge:a.label,actions:h})),s.highlightSkipped&&e.append(Fe(r("highlightSkipped"))),e.append(b),o){let m=f("div",{class:"more"},f("button",{class:"text-btn",part:"show-more",text:r("showMore",{count:dt(s.lineCount,this.locale)}),attrs:{type:"button","data-focus-key":"show-more","aria-expanded":"false"},on:{click:()=>{this.expanded=!0,this.render(),this.root.querySelector(".body")?.focus({preventScroll:!0})}}}));e.append(m)}}applyTabSize(e){let t=Rt(this.getAttribute("tab-size"),{min:1,max:16,fallback:0});t?e.style.setProperty("--_tab-size",String(t)):e.style.removeProperty("--_tab-size")}renderEditor(e,t){let r=this.t,a=this.feature("diff")&&t.name==="plaintext",s=new Ge({text:this.text??"",language:a?"diff":t.name,lineNumbers:this.feature("line-numbers"),wrap:this.wrapped,highlightRanges:fr(this.getAttribute("highlight-lines")),highlightLimit:W().highlightLimit,label:this.heading||`${r("editor")}${t.label?` (${t.label})`:""}`,placeholder:this.getAttribute("placeholder")??void 0,onInput:h=>this.edited(h),onChange:h=>ne(this,te.CHANGE,{value:h}),history:this.editHistory??void 0});this.editor?.destroy(),this.editor=s;let i=null,o={run:h=>(i=new Xt(s.layer.querySelector("pre.code")),i.run(h)),go:h=>Kr(i?.go(h)??null),clear:()=>i?.clear()},c=[this.searchButton(o),this.feature("wrap-toggle")?de({icon:"wrap",label:r("wrap"),key:"wrap",part:"wrap-button",pressed:this.wrapped,onClick:()=>{this.wrapState=!this.wrapped,this.render()}}):null,...this.historyButtons(s),this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(`code.${ho[t.name]??"txt"}`),"text/plain"):null,this.feature("copy")?this.copyButton(()=>this.text??"",r("copyCode")):null],u=f("div",{class:"body editor-body",part:"body"},s.element);e.classList.toggle("wrap",this.wrapped),e.classList.remove("collapsed"),e.append(...this.chrome({badge:t.label,actions:c}),u),s.align()}contentEdited(){this.searchOpen&&this.searchQuery&&this.searchBar?.run()}revealAll(e){e.classList.contains("collapsed")&&(this.expanded=!0,e.classList.remove("collapsed"),e.querySelector(".more")?.remove())}};function sa(n){return n==="plaintext"?"":n==="xml"?"HTML":(He.getLanguage(n)?.name??n).split(",")[0].trim()}var po=`/*
 * Charts: a legend of toggle buttons above the plot (drawn by Apache ECharts in the theme
 * colors), and the data table view.
 */
.vt {
  --_chart-1: var(--vt-chart-1, var(--_accent));
  --_chart-2: var(--vt-chart-2, var(--_info));
  --_chart-3: var(--vt-chart-3, var(--_warning));
  --_chart-4: var(--vt-chart-4, var(--_syntax-keyword));
  --_chart-5: var(--vt-chart-5, var(--_danger));
  --_chart-6: var(--vt-chart-6, var(--_syntax-string));
  --_chart-7: var(--vt-chart-7, var(--_syntax-number));
  --_chart-8: var(--vt-chart-8, var(--_fg-muted));
}

.chart-body {
  padding: var(--_space-3) var(--_space-3) var(--_space-2);
  background: var(--_surface);
}

.plot {
  position: relative;
  width: 100%;
  min-height: 120px;
  border-radius: var(--_radius-sm);
}

.plot:focus-visible {
  outline: 2px solid var(--_accent);
  outline-offset: 2px;
}

.plot > .loading {
  height: 100%;
}

/* ---------- Legend ---------- */

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 var(--_space-1) var(--_space-3);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--_border);
  border-radius: var(--_radius-full);
  background: var(--_surface);
  color: var(--_fg);
  font: 500 var(--_font-size-small) / 1 var(--_font-ui);
  cursor: pointer;
  transition:
    opacity var(--_duration-fast) var(--_easing),
    border-color var(--_duration-fast) var(--_easing);
}

.legend-item:hover {
  border-color: var(--_border-strong);
}

.legend-item[aria-pressed='false'] {
  opacity: 0.45;
}

.legend-item[aria-pressed='false'] .swatch {
  background: transparent;
  box-shadow: inset 0 0 0 2px var(--_c);
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: var(--_c);
}

.s-0 {
  --_c: var(--_chart-1);
}
.s-1 {
  --_c: var(--_chart-2);
}
.s-2 {
  --_c: var(--_chart-3);
}
.s-3 {
  --_c: var(--_chart-4);
}
.s-4 {
  --_c: var(--_chart-5);
}
.s-5 {
  --_c: var(--_chart-6);
}
.s-6 {
  --_c: var(--_chart-7);
}
.s-7 {
  --_c: var(--_chart-8);
}

/* ---------- Table view ---------- */

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--_font-size-ui);
  font-variant-numeric: tabular-nums;
}

.data-table th,
.data-table td {
  padding: 7px var(--_space-3);
  border-bottom: 1px solid var(--_border);
  text-align: right;
  white-space: nowrap;
}

.data-table th:first-child {
  text-align: left;
}

.data-table thead th {
  color: var(--_fg-muted);
  font-size: var(--_font-size-small);
  font-weight: 600;
}

.data-table tbody th {
  font-weight: 500;
}

/* ---------- Edit mode ---------- */

.chart-edit > .editor-body {
  max-height: min(36vh, 300px);
  border-bottom: 1px solid var(--_border);
}
`;var qn=null;function fo(){if(qn)return qn;let n=W().vendorUrl||An(),e={ready:!1,echarts:null,promise:Promise.resolve()};return e.promise=import(new URL("echarts.js",n||location.href).href).then(t=>(e.echarts=t.echarts,e.ready=!0,t.echarts),t=>{throw qn=null,t}),qn=e,e}var Vu=Object.freeze([",",";","	","|"]);function qu(n){let e=n.slice(0,2e4).split(/\r?\n/).slice(0,20).filter(a=>a.trim()),t=",",r=0;for(let a of Vu){let s=e.map(c=>Ku(c,a));if(!s.length||s[0]===0)continue;let o=s.filter(c=>c===s[0]).length/s.length*10+Math.min(s[0],10);o>r&&(t=a,r=o)}return t}function Ku(n,e){let t=0,r=!1;for(let a of n)a==='"'?r=!r:a===e&&!r&&(t+=1);return t}function mo(n,e={}){let t=n.charCodeAt(0)===65279?n.slice(1):n,r=e.delimiter??qu(t),a=[],s=[],i="",o=!1,c=0,u=1,h=0,b=!1,m=0,_=t.length,p=()=>{s.length<1e3?s.push(i):b=!0,i=""},g=()=>{p(),h=Math.max(h,s.length),a.push(s),s=[]};for(;m<_;){let M=t[m];if(o){if(M==='"'){if(t[m+1]==='"'){i+='"',m+=2;continue}o=!1,m+=1;continue}let D=t.indexOf('"',m),j=D===-1?_:D,P=t.slice(m,j);u+=Wu(P),i+=P,m=j;continue}M==='"'&&i===""?(o=!0,c=u,m+=1):M===r?(p(),m+=1):M===`
`||M==="\r"?(g(),m+=M==="\r"&&t[m+1]===`
`?2:1,u+=1):(i+=M,m+=1)}return(i!==""||s.length)&&g(),{rows:a,delimiter:r,columns:h,truncatedColumns:b,error:o?{message:"Unclosed quoted field",line:c}:null}}function Wu(n){let e=0;for(let t=n.indexOf(`
`);t!==-1;t=n.indexOf(`
`,t+1))e+=1;return e}var Ht=5e3,yo=12,ze=class extends Error{};function oa(n){if(typeof n=="number")return Number.isFinite(n)?n:null;if(typeof n!="string")return null;let e=n.trim().replace(/[\s,_](?=\d{3}\b)/g,"").replace(/%$/,"");if(!e||!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(e))return null;let t=Number(e);return Number.isFinite(t)?t:null}function Yu(n){return n?.trim()?n.split(/[\s,]+/).map(e=>e.trim()).filter(Boolean):null}function go(n,e,t){let r=e.length>Ht,a=r?e.slice(0,Ht):e,s=t.x?n.indexOf(t.x):-1;if(t.x&&s<0)throw new ze(`No column named "${t.x}".`);let i=Yu(t.y??null),o;if(i)o=i.map(c=>{let u=n.indexOf(c);if(u<0)throw new ze(`No column named "${c}".`);return u});else{let c=n.map((u,h)=>{let b=a.map(m=>m[h]).filter(m=>m!==""&&m!=null);return b.length>0&&b.filter(m=>oa(m)!==null).length>=b.length*.8});s<0&&(s=c.findIndex(u=>!u)),s<0&&(s=0),o=n.map((u,h)=>h).filter(u=>u!==s&&c[u])}if(s<0&&(s=n.findIndex((c,u)=>!o.includes(u)),s<0&&(s=-1)),!o.length)throw new ze("No numeric column to plot.");return{labels:a.map((c,u)=>String(c[s]??u+1)),series:o.slice(0,yo).map(c=>({name:n[c]||`Series ${c+1}`,values:a.map(u=>oa(u[c]))})),truncated:r}}function bo(n){return Array.isArray(n)?n.slice(0,Ht).map(e=>oa(e)):[]}function vo(n,e={}){let t=n.trim();if(!t)return{labels:[],series:[],truncated:!1};if(/^[[{]/.test(t)){let a;try{a=JSON.parse(t)}catch(s){throw new ze(s instanceof Error?s.message:"Invalid JSON.")}if(Array.isArray(a)&&a.every(s=>typeof s!="object"||s===null)){let s=bo(a);return{labels:s.map((i,o)=>String(o+1)),series:[{name:"Value",values:s}],truncated:a.length>Ht}}if(Array.isArray(a)){let s=a.filter(o=>o&&typeof o=="object"&&!Array.isArray(o)),i=[...new Set(s.flatMap(o=>Object.keys(o)))];return go(i,s.map(o=>i.map(c=>o[c])),e)}if(a&&typeof a=="object"){let s=Array.isArray(a.labels)?a.labels.slice(0,Ht).map(String):[],i=Array.isArray(a.datasets)?a.datasets:Array.isArray(a.series)?a.series:null;if(!i)throw new ze('Expected "labels" with "series" or "datasets".');let o=i.slice(0,yo).map((u,h)=>({name:String(u?.name??u?.label??`Series ${h+1}`),values:bo(Array.isArray(u)?u:u?.data)})),c=Math.max(s.length,...o.map(u=>u.values.length));for(;s.length<c;)s.push(String(s.length+1));return{labels:s,series:o,truncated:c>Ht}}throw new ze("Unsupported JSON shape.")}let{rows:r}=mo(t);if(r.length<2)throw new ze("Expected a header row and at least one data row.");return go(r[0].map(a=>a.trim()),r.slice(1),e)}function xo(n){let e=a=>/[",\n]/.test(a)?`"${a.replace(/"/g,'""')}"`:a,t=["label",...n.series.map(a=>a.name)].map(e).join(","),r=n.labels.map((a,s)=>[e(a),...n.series.map(i=>i.values[s]===null||i.values[s]===void 0?"":String(i.values[s]))].join(","));return[t,...r].join(`
`)}var Zu=["line","area","bar","pie"],Ju=["chart","table"],la=8,ca=class extends $e{static type="chart";static componentAttributes=Object.freeze(["type","stacked","smooth","horizontal","zoom","x","y","height","legend","grid","points","unit","compact","min","max","tabs","view"]);static presets={simple:{grid:!0},full:{header:!0,dot:!0,copy:!0,download:!0,fullscreen:!0,tabs:!0,grid:!0}};static styles=[tt,$t,po];constructor(){super(),this.parsed=null,this.hiddenSeries=new Set,this.viewState=null,this.panelId=_e("panel"),this.plot=null,this.instance=null,this.resize=null,this.active=-1,this.animateIn=!0,this.editor=null,this.previewTimer=void 0}disconnectedCallback(){this.dispose(),clearTimeout(this.previewTimer),this.editor?.destroy(),super.disconnectedCallback()}dispose(){this.resize?.disconnect(),this.resize=null,this.instance?.dispose(),this.instance=null}contentChanged(){this.parsed=null,this.hiddenSeries.clear(),this.animateIn=!0}attributeChangedCallback(e,t,r){(e==="x"||e==="y")&&(this.parsed=null),e==="view"&&(this.viewState=null),super.attributeChangedCallback(e,t,r)}parse(){let e=this.text??"",t=this.getAttribute("x"),r=this.getAttribute("y"),a=`${t}\0${r}\0${e}`;if(this.parsed?.key!==a)try{this.parsed={key:a,data:vo(e,{x:t,y:r}),error:null}}catch(s){this.parsed={key:a,data:null,error:s instanceof Error?s:new ze(String(s))}}return this.parsed}set data(e){super.data=e}get data(){let e=this.parse().data;return e?{labels:[...e.labels],series:e.series.map(t=>({name:t.name,values:[...t.values]})),truncated:e.truncated}:{labels:[],series:[],truncated:!1}}get chartType(){return Ot(this.getAttribute("type"),Zu,"line")}get view(){return this.viewState??Ot(this.getAttribute("view"),Ju,"chart")}format(e){if(e==null||Number.isNaN(e))return"\u2013";let t=this.feature("compact"),r=new Intl.NumberFormat(this.locale,{notation:t?"compact":"standard",maximumFractionDigits:t?1:2}).format(e),a=(this.getAttribute("unit")??"").slice(0,12);return a?`${r}${/^[%‰]$/.test(a)?"":"\u202F"}${a}`:r}renderContent(e){let t=this.t,{data:r,error:a}=this.parse(),s=f("div",{class:"panel",attrs:{id:this.panelId}}),i=[];this.dispose(),this.plot=null;let o;if(a?o=f("div",{class:"body chart-body",part:"body"},Fe(t("chartError",{message:a.message}))):!r||!r.labels.length?o=f("div",{class:"body chart-body",part:"body"},f("div",{class:"empty",part:"empty",text:t("empty")})):this.view==="table"&&!this.editing?o=f("div",{class:"body chart-body",part:"body"},this.table(r)):o=f("div",{class:"body chart-body",part:"body"},...this.chart(r)),this.editing){let b=this.createEditor();s.classList.add("chart-edit"),s.append(f("div",{class:"body editor-body",part:"body source"},b.element),o),i=this.historyButtons(b)}else s.append(o);r?.truncated&&s.prepend(Fe(t("chartTruncated")));let c=this.feature("tabs")&&!this.editing&&r&&!a?Ss({tabs:[{id:"chart",label:t("chartView"),icon:"chart"},{id:"table",label:t("table"),icon:"table"}],selected:this.view,label:t("tabs"),panelId:this.panelId,onSelect:b=>{this.viewState=b,this.animateIn=b==="chart",this.render(),ne(this,te.TAB_CHANGE,{tab:b})}}):null;c&&s.setAttribute("role","tabpanel");let u=()=>r?xo(r):this.text??"",h=[...i,this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(u,this.downloadName("chart.csv"),"text/csv"):null,this.feature("copy")?this.copyButton(u,t("copyData")):null];e.append(...this.chrome({badge:c?"":t("chartView"),tabs:c,actions:h}),s),this.editor?.align(),this.plot&&this.draw()}chart(e){let t=this.t,r=Rt(this.getAttribute("height"),{min:120,max:800,fallback:300}),s=!(this.chartType==="pie")&&_o(this,"legend",e.series.length>1),i=[];if(s){let o=f("div",{class:"legend",part:"legend",attrs:{role:"group","aria-label":t("legend")}});e.series.forEach((c,u)=>{o.append(f("button",{class:`legend-item s-${u%la}`,part:"legend-item",attrs:{type:"button","aria-pressed":String(!this.hiddenSeries.has(u)),"data-focus-key":`series-${u}`,title:t("seriesToggle",{name:c.name})},on:{click:()=>this.toggleSeries(u)}},f("span",{class:"swatch",attrs:{"aria-hidden":"true"}}),c.name))}),i.push(o)}return this.plot=f("div",{class:"plot",part:"plot",attrs:{tabindex:"0",role:"img","aria-roledescription":t("chartView"),"aria-label":this.summary(e)},on:{keydown:o=>this.onKeyDown(o),blur:()=>this.hideTip()}}),this.plot.style.height=`${r}px`,i.push(this.plot),i}toggleSeries(e){let t=this.parse().data;if(!t)return;this.hiddenSeries.has(e)?this.hiddenSeries.delete(e):this.hiddenSeries.size<t.series.length-1&&this.hiddenSeries.add(e),this.root.querySelector(`[data-focus-key="series-${e}"]`)?.setAttribute("aria-pressed",String(!this.hiddenSeries.has(e))),this.instance&&this.instance.setOption(this.option(t),{notMerge:!0})}summary(e){let t=this.t,r=e.series.map(a=>{let s=a.values.filter(i=>i!==null);return t("chartRange",{name:a.name,min:this.format(s.length?Math.min(...s):null),max:this.format(s.length?Math.max(...s):null)})});return`${this.heading?`${this.heading}. `:""}${t("chartSummary",{type:t(`chart_${this.chartType}`),series:dt(e.series.length,this.locale),points:dt(e.labels.length,this.locale)})} ${r.join("; ")}.`}draw(){let e=this.plot;if(!e)return;let t=fo();if(!t.ready){e.replaceChildren(Pt(this.t)),t.promise.then(()=>{this.plot===e&&this.draw()},s=>{this.plot===e&&e.replaceChildren(Fe(this.t("chartLoadFailed",{message:String(s?.message??s)})))});return}let r=this.parse().data;if(!r)return;e.replaceChildren();let a=t.echarts;this.instance=a.init(e,null,{renderer:"canvas",locale:this.locale.startsWith("fr")?"FR":"EN"}),this.instance.setOption(this.option(r)),this.animateIn=!1,this.instance.on("click",s=>{this.active=s.dataIndex??-1,this.select()}),this.resize=new ResizeObserver(()=>this.instance?.resize()),this.resize.observe(e)}palette(){let e=f("span",{attrs:{"aria-hidden":"true"}});e.style.display="none",this.frame.append(e);let t=s=>(e.style.color=`var(${s})`,getComputedStyle(e).color),a={series:Array.from({length:la},(s,i)=>t(`--_chart-${i+1}`)),fg:t("--_fg"),muted:t("--_fg-muted"),border:t("--_border"),surface:t("--_surface-raised"),font:getComputedStyle(this.frame).fontFamily,mono:getComputedStyle(e).getPropertyValue("--_font-mono")||"monospace"};return e.remove(),a}option(e){let t=this.chartType,r=this.palette(),a=matchMedia("(prefers-reduced-motion: reduce)").matches,s=e.series.map((g,S)=>!this.hiddenSeries.has(S)),i=e.series.map((g,S)=>({series:g,index:S})).filter(({index:g})=>s[g]),o={renderMode:"richText",confine:!0,backgroundColor:r.surface,borderColor:r.border,borderWidth:1,padding:[8,10],textStyle:{color:r.fg,fontFamily:r.font,fontSize:12},valueFormatter:g=>this.format(g)},c={animation:!a,animationDuration:this.animateIn?900:400,animationEasing:"cubicOut",animationDurationUpdate:450,textStyle:{fontFamily:r.font,color:r.muted},aria:{enabled:!0,label:{description:this.summary(e)}}};if(t==="pie"){let g=i[0]?.series??e.series[0];return{...c,color:r.series,tooltip:{...o,trigger:"item"},series:[{name:g.name,type:"pie",radius:["46%","74%"],center:["50%","52%"],avoidLabelOverlap:!0,itemStyle:{borderColor:r.surface,borderWidth:2,borderRadius:4},label:{color:r.fg,formatter:"{b}"},labelLine:{lineStyle:{color:r.border}},emphasis:{scaleSize:6},data:e.labels.map((S,M)=>({name:S,value:g.values[M]??0}))}]}}let u=t==="bar"&&this.feature("horizontal"),h=this.feature("stacked")&&t!=="line",b=_o(this,"points",e.labels.length<=60),m=this.feature("zoom"),_={type:"category",data:e.labels,boundaryGap:t==="bar",axisLine:{lineStyle:{color:r.border}},axisTick:{show:!1},axisLabel:{color:r.muted,hideOverlap:!0}},p={type:"value",min:wo(this,"min")??void 0,max:wo(this,"max")??void 0,scale:t==="line",splitLine:{show:this.feature("grid"),lineStyle:{color:r.border,type:"dashed"}},axisLabel:{color:r.muted,formatter:g=>this.format(g)}};return{...c,color:i.map(({index:g})=>r.series[g%la]),grid:{left:12,right:20,top:20,bottom:m?52:12,containLabel:!0},tooltip:{...o,trigger:"axis",axisPointer:{type:t==="bar"?"shadow":"line",lineStyle:{color:r.muted,type:"dashed"},shadowStyle:{color:"rgba(127, 127, 127, 0.08)"}}},xAxis:u?p:_,yAxis:u?{..._,inverse:!0}:p,dataZoom:m?[{type:"inside",[u?"yAxisIndex":"xAxisIndex"]:0},{type:"slider",height:18,bottom:10,borderColor:r.border,fillerColor:"rgba(20, 184, 166, 0.12)",handleStyle:{color:r.series[0]},textStyle:{color:r.muted},dataBackground:{lineStyle:{color:r.border},areaStyle:{color:r.border}}}]:[],series:i.map(({series:g})=>({name:g.name,type:t==="bar"?"bar":"line",data:g.values.map(S=>S===null?"-":S),stack:h?"total":void 0,smooth:t!=="bar"&&this.feature("smooth")?.35:!1,showSymbol:b,symbolSize:6,connectNulls:!1,lineStyle:{width:2.2},areaStyle:t==="area"?{opacity:h?.55:.16}:void 0,barMaxWidth:38,itemStyle:t==="bar"?{borderRadius:u?[0,4,4,0]:[4,4,0,0]}:void 0,emphasis:{focus:"series"},universalTransition:!0}))}}onKeyDown(e){let t=this.parse().data,r=t?.labels.length??0;if(!t||!r||!this.instance)return;let a=this.active,s=null;if(e.key==="ArrowRight"||e.key==="ArrowDown")s=Math.min(r-1,a+1);else if(e.key==="ArrowLeft"||e.key==="ArrowUp")s=Math.max(0,a-1);else if(e.key==="Home")s=0;else if(e.key==="End")s=r-1;else if(e.key==="Escape"){this.hideTip();return}else if((e.key==="Enter"||e.key===" ")&&a>=0){e.preventDefault(),this.select();return}s!==null&&(e.preventDefault(),this.active=s,this.instance.dispatchAction({type:"showTip",seriesIndex:0,dataIndex:s}),this.announce(`${t.labels[s]}: ${t.series.filter((i,o)=>!this.hiddenSeries.has(o)).map(i=>`${i.name} ${this.format(i.values[s]??null)}`).join(", ")}`))}hideTip(){this.active=-1,this.instance?.dispatchAction({type:"hideTip"})}select(){let e=this.parse().data;!e||this.active<0||ne(this,te.SELECT,{index:this.active,label:e.labels[this.active],values:Object.fromEntries(e.series.map(t=>[t.name,t.values[this.active]??null]))})}table(e){return f("table",{class:"data-table",part:"table",attrs:{"aria-label":this.heading||this.t("chartView")}},f("thead",{},f("tr",{},f("th",{attrs:{scope:"col"},text:this.getAttribute("x")||""}),...e.series.map(t=>f("th",{attrs:{scope:"col"},text:t.name})))),f("tbody",{},...e.labels.map((t,r)=>f("tr",{},f("th",{attrs:{scope:"row"},text:t}),...e.series.map(a=>f("td",{text:this.format(a.values[r]??null)}))))))}createEditor(){return this.editor?.destroy(),this.editor=new Ge({text:this.text??"",language:/^\s*[[{]/.test(this.text??"")?"json":"plaintext",lineNumbers:!1,wrap:!1,highlightLimit:W().highlightLimit,label:this.heading||this.t("editor"),placeholder:this.getAttribute("placeholder")??void 0,onInput:e=>this.edited(e),onChange:e=>ne(this,te.CHANGE,{value:e}),history:this.editHistory??void 0}),this.editor}contentEdited(){clearTimeout(this.previewTimer),this.previewTimer=setTimeout(()=>{this.parsed=null;let e=this.parse().data;e&&this.instance?this.instance.setOption(this.option(e),{notMerge:!0}):this.render()},250)}};function _o(n,e,t){return n.getAttribute(e)===null?t:n.feature(e)}function wo(n,e){let t=n.getAttribute(e);if(t===null||t.trim()==="")return null;let r=Number(t);return Number.isFinite(r)?r:null}export{ca as VtChart,ia as VtCode,ta as VtMap,aa as VtStats,Ha as configure};
/*! Bundled license information:

dompurify/dist/purify.es.mjs:
  (*! @license DOMPurify 3.4.17 | (c) Cure53 and other contributors | Released under the Apache license 2.0 and Mozilla Public License 2.0 | github.com/cure53/DOMPurify/blob/3.4.17/LICENSE *)
  (*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/babel/babel/blob/main/packages/babel-helpers/LICENSE *)
*/
