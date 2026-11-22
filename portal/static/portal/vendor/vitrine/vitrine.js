/*! Vitrine 0.14.0 | MIT | ecrou-exact/vitrine | See LICENSE and THIRD_PARTY_NOTICES.md */
var So=Object.create;var kr=Object.defineProperty;var ko=Object.getOwnPropertyDescriptor;var No=Object.getOwnPropertyNames;var Co=Object.getPrototypeOf,Lo=Object.prototype.hasOwnProperty;var Ro=(t,e)=>()=>{try{return e||t((e={exports:{}}).exports,e),e.exports}catch(n){throw e=0,n}};var Mo=(t,e,n,a)=>{if(e&&typeof e=="object"||typeof e=="function")for(let r of No(e))!Lo.call(t,r)&&r!==n&&kr(t,r,{get:()=>e[r],enumerable:!(a=ko(e,r))||a.enumerable});return t};var Oo=(t,e,n)=>(n=t!=null?So(Co(t)):{},Mo(e||!t||!t.__esModule?kr(n,"default",{value:t,enumerable:!0}):n,t));var Fs=Ro((Pd,js)=>{function Ns(t){return t instanceof Map?t.clear=t.delete=t.set=function(){throw new Error("map is read-only")}:t instanceof Set&&(t.add=t.clear=t.delete=function(){throw new Error("set is read-only")}),Object.freeze(t),Object.getOwnPropertyNames(t).forEach(e=>{let n=t[e],a=typeof n;(a==="object"||a==="function")&&!Object.isFrozen(n)&&Ns(n)}),t}var An=class{constructor(e){e.data===void 0&&(e.data={}),this.data=e.data,this.isMatchIgnored=!1}ignoreMatch(){this.isMatchIgnored=!0}};function Cs(t){return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;")}function Xe(t,...e){let n=Object.create(null);for(let a in t)n[a]=t[a];return e.forEach(function(a){for(let r in a)n[r]=a[r]}),n}var xl="</span>",ws=t=>!!t.scope,_l=(t,{prefix:e})=>{if(t.startsWith("language:"))return t.replace("language:","language-");if(t.includes(".")){let n=t.split(".");return[`${e}${n.shift()}`,...n.map((a,r)=>`${a}${"_".repeat(r+1)}`)].join(" ")}return`${e}${t}`},Ta=class{constructor(e,n){this.buffer="",this.classPrefix=n.classPrefix,e.walk(this)}addText(e){this.buffer+=Cs(e)}openNode(e){if(!ws(e))return;let n=_l(e.scope,{prefix:this.classPrefix});this.span(n)}closeNode(e){ws(e)&&(this.buffer+=xl)}value(){return this.buffer}span(e){this.buffer+=`<span class="${e}">`}},Es=(t={})=>{let e={children:[]};return Object.assign(e,t),e},Sa=class t{constructor(){this.rootNode=Es(),this.stack=[this.rootNode]}get top(){return this.stack[this.stack.length-1]}get root(){return this.rootNode}add(e){this.top.children.push(e)}openNode(e){let n=Es({scope:e});this.add(n),this.stack.push(n)}closeNode(){if(this.stack.length>1)return this.stack.pop()}closeAllNodes(){for(;this.closeNode(););}toJSON(){return JSON.stringify(this.rootNode,null,4)}walk(e){return this.constructor._walk(e,this.rootNode)}static _walk(e,n){return typeof n=="string"?e.addText(n):n.children&&(e.openNode(n),n.children.forEach(a=>this._walk(e,a)),e.closeNode(n)),e}static _collapse(e){typeof e!="string"&&e.children&&(e.children.every(n=>typeof n=="string")?e.children=[e.children.join("")]:e.children.forEach(n=>{t._collapse(n)}))}},ka=class extends Sa{constructor(e){super(),this.options=e}addText(e){e!==""&&this.add(e)}startScope(e){this.openNode(e)}endScope(){this.closeNode()}__addSublanguage(e,n){let a=e.root;n&&(a.scope=`language:${n}`),this.add(a)}toHTML(){return new Ta(this,this.options).value()}finalize(){return this.closeAllNodes(),!0}};function qt(t){return t?typeof t=="string"?t:t.source:null}function Ls(t){return dt("(?=",t,")")}function wl(t){return dt("(?:",t,")*")}function El(t){return dt("(?:",t,")?")}function dt(...t){return t.map(n=>qt(n)).join("")}function Al(t){let e=t[t.length-1];return typeof e=="object"&&e.constructor===Object?(t.splice(t.length-1,1),e):{}}function Sn(...t){return"("+(Al(t).capture?"":"?:")+t.map(a=>qt(a)).join("|")+")"}function Rs(t){return new RegExp(t.toString()+"|").exec("").length-1}function Tl(t,e){let n=t&&t.exec(e);return n&&n.index===0}var Sl=new RegExp(Sn(/\[(?:[^\\\]]|\\.)*\]/,/\(\?<(?![=!])[^>]+>/,/\(\?'[^']+'/,/\(\??/,/\\([1-9][0-9]*)/,/\\./));function Ca(t,{joinWith:e}){let n=0;return t.map(a=>{n+=1;let r=n,i=qt(a),s="";for(;i.length>0;){let l=Sl.exec(i);if(!l){s+=i;break}s+=i.substring(0,l.index),i=i.substring(l.index+l[0].length),l[0][0]==="\\"&&l[1]?s+="\\"+String(Number(l[1])+r):(s+=l[0],(l[0]==="("||/^\(\?[<']/.test(l[0]))&&n++)}return s}).map(a=>`(${a})`).join(e)}var kl=/\b\B/,Ms="[a-zA-Z]\\w*",La="[a-zA-Z_]\\w*",Os="\\b\\d+(\\.\\d+)?",Is="(-?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)",Ds="\\b(0b[01]+)",Nl="!|!=|!==|%|%=|&|&&|&=|\\*|\\*=|\\+|\\+=|,|-|-=|/=|/|:|;|<<|<<=|<=|<|===|==|=|>>>=|>>=|>=|>>>|>>|>|\\?|\\[|\\{|\\(|\\^|\\^=|\\||\\|=|\\|\\||~",Cl=(t={})=>{let e=/^#![ ]*\//;return t.binary&&(t.begin=dt(e,/.*\b/,t.binary,/\b.*/)),Xe({scope:"meta",begin:e,end:/$/,relevance:0,"on:begin":(n,a)=>{n.index!==0&&a.ignoreMatch()}},t)},Kt={begin:"\\\\[\\s\\S]",relevance:0},Ll={scope:"string",begin:"'",end:"'",illegal:"\\n",contains:[Kt]},Rl={scope:"string",begin:'"',end:'"',illegal:"\\n",contains:[Kt]},Ml={begin:/\b(a|an|the|are|I'm|isn't|don't|doesn't|won't|but|just|should|pretty|simply|enough|gonna|going|wtf|so|such|will|you|your|they|like|more)\b/},kn=function(t,e,n={}){let a=Xe({scope:"comment",begin:t,end:e,contains:[]},n);a.contains.push({scope:"doctag",begin:"[ ]*(?=(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):)",end:/(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):/,excludeBegin:!0,relevance:0});let r=Sn("I","a","is","so","us","to","at","if","in","it","on",/[A-Za-z]+['](d|ve|re|ll|t|s|n)/,/[A-Za-z]+[-][a-z]+/,/[A-Za-z][a-z]{2,}/);return a.contains.push({begin:dt(/[ ]+/,"(",r,/[.]?[:]?([.][ ]|[ ])/,"){3}")}),a},Ol=kn("//","$"),Il=kn("/\\*","\\*/"),Dl=kn("#","$"),Pl={scope:"number",begin:Os,relevance:0},Bl={scope:"number",begin:Is,relevance:0},zl={scope:"number",begin:Ds,relevance:0},Ul={scope:"regexp",begin:/\/(?=[^/\n]*\/)/,end:/\/[gimuy]*/,contains:[Kt,{begin:/\[/,end:/\]/,relevance:0,contains:[Kt]}]},jl={scope:"title",begin:Ms,relevance:0},Fl={scope:"title",begin:La,relevance:0},$l={begin:"\\.\\s*"+La,relevance:0},Hl=function(t){return Object.assign(t,{"on:begin":(e,n)=>{n.data._beginMatch=e[1]},"on:end":(e,n)=>{n.data._beginMatch!==e[1]&&n.ignoreMatch()}})},En=Object.freeze({__proto__:null,APOS_STRING_MODE:Ll,BACKSLASH_ESCAPE:Kt,BINARY_NUMBER_MODE:zl,BINARY_NUMBER_RE:Ds,COMMENT:kn,C_BLOCK_COMMENT_MODE:Il,C_LINE_COMMENT_MODE:Ol,C_NUMBER_MODE:Bl,C_NUMBER_RE:Is,END_SAME_AS_BEGIN:Hl,HASH_COMMENT_MODE:Dl,IDENT_RE:Ms,MATCH_NOTHING_RE:kl,METHOD_GUARD:$l,NUMBER_MODE:Pl,NUMBER_RE:Os,PHRASAL_WORDS_MODE:Ml,QUOTE_STRING_MODE:Rl,REGEXP_MODE:Ul,RE_STARTERS_RE:Nl,SHEBANG:Cl,TITLE_MODE:jl,UNDERSCORE_IDENT_RE:La,UNDERSCORE_TITLE_MODE:Fl});function Gl(t,e){t.input[t.index-1]==="."&&e.ignoreMatch()}function Vl(t,e){t.className!==void 0&&(t.scope=t.className,delete t.className)}function ql(t,e){e&&t.beginKeywords&&(t.begin="\\b("+t.beginKeywords.split(" ").join("|")+")(?!\\.)(?=\\b|\\s)",t.__beforeBegin=Gl,t.keywords=t.keywords||t.beginKeywords,delete t.beginKeywords,t.relevance===void 0&&(t.relevance=0))}function Kl(t,e){Array.isArray(t.illegal)&&(t.illegal=Sn(...t.illegal))}function Wl(t,e){if(t.match){if(t.begin||t.end)throw new Error("begin & end are not supported with match");t.begin=t.match,delete t.match}}function Yl(t,e){t.relevance===void 0&&(t.relevance=1)}var Zl=(t,e)=>{if(!t.beforeMatch)return;if(t.starts)throw new Error("beforeMatch cannot be used with starts");let n=Object.assign({},t);Object.keys(t).forEach(a=>{delete t[a]}),t.keywords=n.keywords,t.begin=dt(n.beforeMatch,Ls(n.begin)),t.starts={relevance:0,contains:[Object.assign(n,{endsParent:!0})]},t.relevance=0,delete n.beforeMatch},Jl=["of","and","for","in","not","or","if","then","parent","list","value"],Xl="keyword";function Ps(t,e,n=Xl){let a=Object.create(null);return typeof t=="string"?r(n,t.split(" ")):Array.isArray(t)?r(n,t):Object.keys(t).forEach(function(i){Object.assign(a,Ps(t[i],e,i))}),a;function r(i,s){e&&(s=s.map(l=>l.toLowerCase())),s.forEach(function(l){let c=l.split("|");a[c[0]]=[i,Ql(c[0],c[1])]})}}function Ql(t,e){return e?Number(e):ec(t)?0:1}function ec(t){return Jl.includes(t.toLowerCase())}var As={},ut=t=>{console.error(t)},Ts=(t,...e)=>{console.log(`WARN: ${t}`,...e)},Mt=(t,e)=>{As[`${t}/${e}`]||(console.log(`Deprecated as of ${t}. ${e}`),As[`${t}/${e}`]=!0)},Tn=new Error;function Bs(t,e,{key:n}){let a=0,r=t[n],i={},s={};for(let l=1;l<=e.length;l++)s[l+a]=r[l],i[l+a]=!0,a+=Rs(e[l-1]);t[n]=s,t[n]._emit=i,t[n]._multi=!0}function tc(t){if(Array.isArray(t.begin)){if(t.skip||t.excludeBegin||t.returnBegin)throw ut("skip, excludeBegin, returnBegin not compatible with beginScope: {}"),Tn;if(typeof t.beginScope!="object"||t.beginScope===null)throw ut("beginScope must be object"),Tn;Bs(t,t.begin,{key:"beginScope"}),t.begin=Ca(t.begin,{joinWith:""})}}function nc(t){if(Array.isArray(t.end)){if(t.skip||t.excludeEnd||t.returnEnd)throw ut("skip, excludeEnd, returnEnd not compatible with endScope: {}"),Tn;if(typeof t.endScope!="object"||t.endScope===null)throw ut("endScope must be object"),Tn;Bs(t,t.end,{key:"endScope"}),t.end=Ca(t.end,{joinWith:""})}}function ac(t){t.scope&&typeof t.scope=="object"&&t.scope!==null&&(t.beginScope=t.scope,delete t.scope)}function rc(t){ac(t),typeof t.beginScope=="string"&&(t.beginScope={_wrap:t.beginScope}),typeof t.endScope=="string"&&(t.endScope={_wrap:t.endScope}),tc(t),nc(t)}function sc(t){function e(s,l){return new RegExp(qt(s),"m"+(t.case_insensitive?"i":"")+(t.unicodeRegex?"u":"")+(l?"g":""))}class n{constructor(){this.matchIndexes={},this.regexes=[],this.matchAt=1,this.position=0}addRule(l,c){c.position=this.position++,this.matchIndexes[this.matchAt]=c,this.regexes.push([c,l]),this.matchAt+=Rs(l)+1}compile(){this.regexes.length===0&&(this.exec=()=>null);let l=this.regexes.map(c=>c[1]);this.matcherRe=e(Ca(l,{joinWith:"|"}),!0),this.lastIndex=0}exec(l){this.matcherRe.lastIndex=this.lastIndex;let c=this.matcherRe.exec(l);if(!c)return null;let d=c.findIndex((x,b)=>b>0&&x!==void 0),p=this.matchIndexes[d];return c.splice(0,d),Object.assign(c,p)}}class a{constructor(){this.rules=[],this.multiRegexes=[],this.count=0,this.lastIndex=0,this.regexIndex=0}getMatcher(l){if(this.multiRegexes[l])return this.multiRegexes[l];let c=new n;return this.rules.slice(l).forEach(([d,p])=>c.addRule(d,p)),c.compile(),this.multiRegexes[l]=c,c}resumingScanAtSamePosition(){return this.regexIndex!==0}considerAll(){this.regexIndex=0}addRule(l,c){this.rules.push([l,c]),c.type==="begin"&&this.count++}exec(l){let c=this.getMatcher(this.regexIndex);c.lastIndex=this.lastIndex;let d=c.exec(l);if(this.resumingScanAtSamePosition()&&!(d&&d.index===this.lastIndex)){let p=this.getMatcher(0);p.lastIndex=this.lastIndex+1,d=p.exec(l)}return d&&(this.regexIndex+=d.position+1,this.regexIndex===this.count&&this.considerAll()),d}}function r(s){let l=new a;return s.contains.forEach(c=>l.addRule(c.begin,{rule:c,type:"begin"})),s.terminatorEnd&&l.addRule(s.terminatorEnd,{type:"end"}),s.illegal&&l.addRule(s.illegal,{type:"illegal"}),l}function i(s,l){let c=s;if(s.isCompiled)return c;[Vl,Wl,rc,Zl].forEach(p=>p(s,l)),t.compilerExtensions.forEach(p=>p(s,l)),s.__beforeBegin=null,[ql,Kl,Yl].forEach(p=>p(s,l)),s.isCompiled=!0;let d=null;return typeof s.keywords=="object"&&s.keywords.$pattern&&(s.keywords=Object.assign({},s.keywords),d=s.keywords.$pattern,delete s.keywords.$pattern),d=d||/\w+/,s.keywords&&(s.keywords=Ps(s.keywords,t.case_insensitive)),c.keywordPatternRe=e(d,!0),l&&(s.begin||(s.begin=/\B|\b/),c.beginRe=e(c.begin),!s.end&&!s.endsWithParent&&(s.end=/\B|\b/),s.end&&(c.endRe=e(c.end)),c.terminatorEnd=qt(c.end)||"",s.endsWithParent&&l.terminatorEnd&&(c.terminatorEnd+=(s.end?"|":"")+l.terminatorEnd)),s.illegal&&(c.illegalRe=e(s.illegal)),s.contains||(s.contains=[]),s.contains=[].concat(...s.contains.map(function(p){return ic(p==="self"?s:p)})),s.contains.forEach(function(p){i(p,c)}),s.starts&&i(s.starts,l),c.matcher=r(c),c}if(t.compilerExtensions||(t.compilerExtensions=[]),t.contains&&t.contains.includes("self"))throw new Error("ERR: contains `self` is not supported at the top-level of a language.  See documentation.");return t.classNameAliases=Xe(t.classNameAliases||{}),i(t)}function zs(t){return t?t.endsWithParent||zs(t.starts):!1}function ic(t){return t.variants&&!t.cachedVariants&&(t.cachedVariants=t.variants.map(function(e){return Xe(t,{variants:null},e)})),t.cachedVariants?t.cachedVariants:zs(t)?Xe(t,{starts:t.starts?Xe(t.starts):null}):Object.isFrozen(t)?Xe(t):t}var oc="11.12.0",Na=class extends Error{constructor(e,n){super(e),this.name="HTMLInjectionError",this.html=n}},Aa=Cs,Ss=Xe,ks=Symbol("nomatch"),lc=7,Us=function(t){let e=Object.create(null),n=Object.create(null),a=[],r=!0,i="Could not find the language '{}', did you forget to load/include a language module?",s={disableAutodetect:!0,name:"Plain text",contains:[]},l={ignoreUnescapedHTML:!1,throwUnescapedHTML:!1,noHighlightRe:/^(no-?highlight)$/i,languageDetectRe:/\blang(?:uage)?-([\w-]+)\b/i,classPrefix:"hljs-",cssSelector:"pre code",languages:null,__emitter:ka};function c(_){return l.noHighlightRe.test(_)}function d(_){let S=_.className+" ";S+=_.parentNode?_.parentNode.className:"";let R=l.languageDetectRe.exec(S);if(R){let j=re(R[1]);return j||(Ts(i.replace("{}",R[1])),Ts("Falling back to no-highlight mode for this block.",_)),j?R[1]:"no-highlight"}return S.split(/\s+/).find(j=>c(j)||re(j))}function p(_,S,R){let j="",E="";typeof S=="object"?(j=_,R=S.ignoreIllegals,E=S.language):(Mt("10.7.0","highlight(lang, code, ...args) has been deprecated."),Mt("10.7.0",`Please use highlight(code, options) instead.
https://github.com/highlightjs/highlight.js/issues/2277`),E=_,j=S),R===void 0&&(R=!0);let L={code:j,language:E};ke("before:highlight",L);let D=L.result?L.result:x(L.language,L.code,R);return D.code=L.code,ke("after:highlight",D),D}function x(_,S,R,j){let E=Object.create(null);function L(A,k){return A.keywords[k]}function D(){if(!T.keywords){Y.addText(V);return}let A=0;T.keywordPatternRe.lastIndex=0;let k=T.keywordPatternRe.exec(V),M="";for(;k;){M+=V.substring(A,k.index);let F=Ee.case_insensitive?k[0].toLowerCase():k[0],ee=L(T,F);if(ee){let[Ae,vt]=ee;if(Y.addText(M),M="",E[F]=(E[F]||0)+1,E[F]<=lc&&(rt+=vt),Ae.startsWith("_"))M+=k[0];else{let xt=Ee.classNameAliases[Ae]||Ae;Q(k[0],xt)}}else M+=k[0];A=T.keywordPatternRe.lastIndex,k=T.keywordPatternRe.exec(V)}M+=V.substring(A),Y.addText(M)}function W(){if(V==="")return;let A=null;if(typeof T.subLanguage=="string"){if(!e[T.subLanguage]){Y.addText(V);return}A=x(T.subLanguage,V,!0,bt[T.subLanguage]),bt[T.subLanguage]=A._top}else A=w(V,T.subLanguage.length?T.subLanguage:null);T.relevance>0&&(rt+=A.relevance),Y.__addSublanguage(A._emitter,A.language)}function z(){T.subLanguage!=null?W():D(),V=""}function Q(A,k){A!==""&&(Y.startScope(k),Y.addText(A),Y.endScope())}function K(A,k){let M=1,F=k.length-1;for(;M<=F;){if(!A._emit[M]){M++;continue}let ee=Ee.classNameAliases[A[M]]||A[M],Ae=k[M];ee?Q(Ae,ee):(V=Ae,D(),V=""),M++}}function an(A,k){return A.scope&&typeof A.scope=="string"&&Y.openNode(Ee.classNameAliases[A.scope]||A.scope),A.beginScope&&(A.beginScope._wrap?(Q(V,Ee.classNameAliases[A.beginScope._wrap]||A.beginScope._wrap),V=""):A.beginScope._multi&&(K(A.beginScope,k),V="")),T=Object.create(A,{parent:{value:T}}),T}function rn(A,k,M){let F=Tl(A.endRe,M);if(F){if(A["on:end"]){let ee=new An(A);A["on:end"](k,ee),ee.isMatchIgnored&&(F=!1)}if(F){for(;A.endsParent&&A.parent;)A=A.parent;return A}}if(A.endsWithParent)return rn(A.parent,k,M)}function $n(A){return T.matcher.regexIndex===0?(V+=A[0],1):(st=!0,0)}function Hn(A){let k=A[0],M=A.rule,F=new An(M),ee=[M.__beforeBegin,M["on:begin"]];for(let Ae of ee)if(Ae&&(Ae(A,F),F.isMatchIgnored))return $n(k);return M.skip?V+=k:(M.excludeBegin&&(V+=k),z(),!M.returnBegin&&!M.excludeBegin&&(V=k)),an(M,A),M.returnBegin?0:k.length}function Gn(A){let k=A[0],M=S.substring(A.index),F=rn(T,A,M);if(!F)return ks;let ee=T;T.endScope&&T.endScope._wrap?(z(),Q(k,T.endScope._wrap)):T.endScope&&T.endScope._multi?(z(),K(T.endScope,A)):ee.skip?V+=k:(ee.returnEnd||ee.excludeEnd||(V+=k),z(),ee.excludeEnd&&(V=k));do T.scope&&Y.closeNode(),!T.skip&&!T.subLanguage&&(rt+=T.relevance),T=T.parent;while(T!==F.parent);return F.starts&&an(F.starts,A),ee.returnEnd?0:k.length}function Vn(){let A=[];for(let k=T;k!==Ee;k=k.parent)k.scope&&A.unshift(k.scope);A.forEach(k=>Y.openNode(k))}let nt={};function sn(A,k){let M=k&&k[0];if(V+=A,M==null)return z(),0;if(nt.type==="begin"&&k.type==="end"&&nt.index===k.index&&M===""){if(V+=S.slice(k.index,k.index+1),!r){let F=new Error(`0 width match regex (${_})`);throw F.languageName=_,F.badRule=nt.rule,F}return 1}if(nt=k,k.type==="begin")return Hn(k);if(k.type==="illegal"&&!R){let F=new Error('Illegal lexeme "'+M+'" for mode "'+(T.scope||"<unnamed>")+'"');throw F.mode=T,F}else if(k.type==="end"){let F=Gn(k);if(F!==ks)return F}if(k.type==="illegal"&&M==="")return k.index===S.length||(V+=`
`),1;if(yt>1e5&&yt>k.index*3)throw new Error("potential infinite loop, way more iterations than matches");return V+=M,M.length}let Ee=re(_);if(!Ee)throw ut(i.replace("{}",_)),new Error('Unknown language: "'+_+'"');let Z=sc(Ee),at="",T=j||Z,bt={},Y=new l.__emitter(l);Vn();let V="",rt=0,me=0,yt=0,st=!1;try{if(Ee.__emitTokens)Ee.__emitTokens(S,Y);else{for(T.matcher.considerAll();;){yt++,st?st=!1:T.matcher.considerAll(),T.matcher.lastIndex=me;let A=T.matcher.exec(S);if(!A)break;let k=S.substring(me,A.index),M=sn(k,A);me=A.index+M}sn(S.substring(me))}return Y.finalize(),at=Y.toHTML(),{language:_,value:at,relevance:rt,illegal:!1,_emitter:Y,_top:T}}catch(A){if(A.message&&A.message.includes("Illegal"))return{language:_,value:Aa(S),illegal:!0,relevance:0,_illegalBy:{message:A.message,index:me,context:S.slice(me-100,me+100),mode:A.mode,resultSoFar:at},_emitter:Y};if(r)return{language:_,value:Aa(S),illegal:!1,relevance:0,errorRaised:A,_emitter:Y,_top:T};throw A}}function b(_){let S={value:Aa(_),illegal:!1,relevance:0,_top:s,_emitter:new l.__emitter(l)};return S._emitter.addText(_),S}function w(_,S){S=S||l.languages||Object.keys(e);let R=b(_),j=S.filter(re).filter(Se).map(z=>x(z,_,!1));j.unshift(R);let E=j.sort((z,Q)=>{if(z.relevance!==Q.relevance)return Q.relevance-z.relevance;if(z.language&&Q.language){if(re(z.language).supersetOf===Q.language)return 1;if(re(Q.language).supersetOf===z.language)return-1}return 0}),[L,D]=E,W=L;return W.secondBest=D,W}function h(_,S,R){let j=S&&n[S]||R;_.classList.add("hljs"),_.classList.add(`language-${j}`)}function y(_){let S=null,R=d(_);if(c(R))return;if(ke("before:highlightElement",{el:_,language:R}),_.dataset.highlighted){console.log("Element previously highlighted. To highlight again, first unset `dataset.highlighted`.",_);return}if(_.children.length>0&&(l.ignoreUnescapedHTML||(console.warn("One of your code blocks includes unescaped HTML. This is a potentially serious security risk."),console.warn("https://github.com/highlightjs/highlight.js/wiki/security"),console.warn("The element with unescaped HTML:"),console.warn(_)),l.throwUnescapedHTML))throw new Na("One of your code blocks includes unescaped HTML.",_.innerHTML);S=_;let j=S.textContent,E=R?p(j,{language:R,ignoreIllegals:!0}):w(j);_.innerHTML=E.value,_.dataset.highlighted="yes",h(_,R,E.language),_.result={language:E.language,re:E.relevance,relevance:E.relevance},E.secondBest&&(_.secondBest={language:E.secondBest.language,relevance:E.secondBest.relevance}),ke("after:highlightElement",{el:_,result:E,text:j})}function N(_){l=Ss(l,_)}let I=()=>{B(),Mt("10.6.0","initHighlighting() deprecated.  Use highlightAll() now.")};function P(){B(),Mt("10.6.0","initHighlightingOnLoad() deprecated.  Use highlightAll() now.")}let H=!1;function B(){function _(){B()}if(document.readyState==="loading"){H||window.addEventListener("DOMContentLoaded",_,!1),H=!0;return}document.querySelectorAll(l.cssSelector).forEach(y)}function q(_,S){let R=null;try{R=S(t)}catch(j){if(ut("Language definition for '{}' could not be registered.".replace("{}",_)),r)ut(j);else throw j;R=s}R.name||(R.name=_),e[_]=R,R.rawDefinition=S.bind(null,t),R.aliases&&Re(R.aliases,{languageName:_})}function X(_){delete e[_];for(let S of Object.keys(n))n[S]===_&&delete n[S]}function ne(){return Object.keys(e)}function re(_){return _=(_||"").toLowerCase(),e[_]||e[n[_]]}function Re(_,{languageName:S}){typeof _=="string"&&(_=[_]),_.forEach(R=>{n[R.toLowerCase()]=S})}function Se(_){let S=re(_);return S&&!S.disableAutodetect}function ae(_){_["before:highlightBlock"]&&!_["before:highlightElement"]&&(_["before:highlightElement"]=S=>{_["before:highlightBlock"](Object.assign({block:S.el},S))}),_["after:highlightBlock"]&&!_["after:highlightElement"]&&(_["after:highlightElement"]=S=>{_["after:highlightBlock"](Object.assign({block:S.el},S))})}function ye(_){ae(_),a.push(_)}function Pe(_){let S=a.indexOf(_);S!==-1&&a.splice(S,1)}function ke(_,S){let R=_;a.forEach(function(j){j[R]&&j[R](S)})}function Me(_){return Mt("10.7.0","highlightBlock will be removed entirely in v12.0"),Mt("10.7.0","Please use highlightElement now."),y(_)}Object.assign(t,{highlight:p,highlightAuto:w,highlightAll:B,highlightElement:y,highlightBlock:Me,configure:N,initHighlighting:I,initHighlightingOnLoad:P,registerLanguage:q,unregisterLanguage:X,listLanguages:ne,getLanguage:re,registerAliases:Re,autoDetection:Se,inherit:Ss,addPlugin:ye,removePlugin:Pe}),t.debugMode=function(){r=!1},t.safeMode=function(){r=!0},t.versionString=oc,t.regex={concat:dt,lookahead:Ls,either:Sn,optional:El,anyNumberOfTimes:wl};for(let _ in En)typeof En[_]=="object"&&Ns(En[_]);return Object.assign(t,En),t},Ot=Us({});Ot.newInstance=()=>Us({});js.exports=Ot;Ot.HighlightJS=Ot;Ot.default=Ot});var Nr=`/*
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
`;function Ie(t){if(t===null)return null;let e=t.trim().toLowerCase();return!(e==="false"||e==="off"||e==="no"||e==="0")}function fn(t,{min:e,max:n,fallback:a}){if(t===null||t.length>32)return a;let r=t.trim();if(!/^[+-]?\d+$/.test(r))return a;let i=Number(r);return Number.isSafeInteger(i)?Math.min(n,Math.max(e,i)):a}function ca(t,e,n){if(t===null)return n;let a=t.trim().toLowerCase();return e.includes(a)?a:n}var Do=500;function ua(t){if(!t||t.length>1e3*10)return[];let e=[];for(let a of t.split(",")){if(e.length>=Do)break;let r=/^\s*(\d{1,9})\s*(?:-\s*(\d{1,9})\s*)?$/.exec(a);if(!r)continue;let i=Number(r[1]),s=r[2]===void 0?i:Number(r[2]);e.push([Math.min(i,s),Math.max(i,s)])}e.sort((a,r)=>a[0]-r[0]);let n=[];for(let a of e){let r=n[n.length-1];r&&a[0]<=r[1]+1?r[1]=Math.max(r[1],a[1]):n.push([a[0],a[1]])}return n}function Cr(t,e){let n=0,a=e.length-1;for(;n<=a;){let r=n+a>>1,[i,s]=e[r];if(t<i)a=r-1;else if(t>s)n=r+1;else return!0}return!1}function Lr(t){if(t===null)return null;let e=t.trim().toLowerCase();return/^\d{1,6}(?:\.\d{1,4})?(?:px|em|rem|vh|svh|lvh|dvh|%|ch|lh)$/.test(e)?e:null}function Rr(t,e=200){if(!t)return"";let a=t.slice(0,e*4).replace(/[\u0000-\u001f\u007f-\u009f]/g,"").replace(/\s+/g," ").trim();return a.length>e?a.slice(0,e-1)+"\u2026":a}function Mr(t,e){let n=(t??"").split(/[\\/]/).pop()??"",a=/[\u0000-\u001f\u007f<>:"|?*]/g;return n.replace(a,"").replace(/^[.\s]+/,"").trim().slice(0,120)||e}var Or=`/*
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
`;var Ir=`/*
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
`;var Nt=`/*
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
`;async function da(t,e=document){if(navigator.clipboard&&window.isSecureContext)try{return await navigator.clipboard.writeText(t),!0}catch{}return Uo(t,e)}function Uo(t,e){let n=document.createElement("textarea");n.value=t,n.setAttribute("readonly",""),n.setAttribute("aria-hidden","true"),n.style.position="fixed",n.style.opacity="0",n.style.pointerEvents="none",(e instanceof Document?e.body:e).appendChild(n);try{return n.select(),document.execCommand("copy")}catch{return!1}finally{n.remove()}}function Dr(t,e,n="text/plain"){let a=new Blob([t],{type:`${n};charset=utf-8`}),r=URL.createObjectURL(a),i=document.createElement("a");i.href=r,i.download=e,i.rel="noopener",i.style.display="none",document.body.appendChild(i),i.click(),i.remove(),setTimeout(()=>URL.revokeObjectURL(r),1e3)}var pa=Object.freeze({theme:"auto",lightTheme:"light",darkTheme:"dark",lang:"en",maxSize:2097152,highlightLimit:3e5,maxDepth:512,fetchTimeout:15e3,languagesUrl:"",syntaxTheme:"",syntaxThemeDark:"",syntaxThemesUrl:"",vendorUrl:""}),jo=Object.freeze({maxSize:50*1024*1024,highlightLimit:5*1024*1024,maxDepth:1e4,fetchTimeout:12e4}),Ct={...pa},ha=new Set;function J(){return Object.freeze({...Ct})}function Pr(t){if(!t||typeof t!="object")return J();let e={...Ct};for(let[a,r]of Object.entries(t))Fo(a,r);let n=new Set(Object.keys(Ct).filter(a=>Ct[a]!==e[a]));if(n.size)for(let a of ha)a(n);return J()}function Fo(t,e){if(!Object.prototype.hasOwnProperty.call(pa,t)){console.warn(`[vitrine] Unknown configuration option "${t}".`);return}let n=t;if(typeof pa[n]==="number"){let r=jo[n];if(typeof e!="number"||!Number.isFinite(e)||e<=0){console.warn(`[vitrine] Option "${t}" must be a positive number.`);return}Ct[n]=Math.min(Math.floor(e),r??e);return}if(typeof e!="string"||e.length>2048){console.warn(`[vitrine] Option "${t}" must be a string.`);return}Ct[n]=e.trim()}function Br(t){return ha.add(t),()=>ha.delete(t)}function g(t,e={},...n){let a=document.createElement(t);if(e.class&&(a.className=e.class),e.part&&a.setAttribute("part",e.part),e.attrs)for(let[r,i]of Object.entries(e.attrs))i===!1||i===null||i===void 0||a.setAttribute(r,i===!0?"":String(i));if(e.text!==void 0&&(a.textContent=e.text),e.on)for(let[r,i]of Object.entries(e.on))a.addEventListener(r,i);return $o(a,n),a}function $o(t,e){for(let n of e)n==null||n===!1||t.append(typeof n=="string"?document.createTextNode(n):n)}var zr=0;function Ne(t){return zr+=1,`vt-${t}-${zr}`}function mn(t){let e=t.replace(/\r\n?/g,`
`).split(`
`);for(;e.length&&e[0].trim()==="";)e.shift();for(;e.length&&e[e.length-1].trim()==="";)e.pop();let n=1/0;for(let a of e){if(a.trim()==="")continue;let r=/^[ \t]*/.exec(a);if(n=Math.min(n,r?r[0].length:0),n===0)break}return!Number.isFinite(n)||n===0?e.join(`
`):e.map(a=>a.slice(n)).join(`
`)}function Ur(t,e){let n,a=(...r)=>{clearTimeout(n),n=setTimeout(()=>t(...r),e)};return a.cancel=()=>clearTimeout(n),a}var Ho=new Set(["http:","https:","mailto:","tel:"]),Go=/^data:image\/(?:png|gif|jpe?g|webp|avif);base64,[a-z0-9+/]+=*$/i;function jr(t,e={}){if(typeof t!="string")return!1;let n=0,a=t.length;for(;n<a&&t.charCodeAt(n)<=32;)n+=1;for(;a>n&&t.charCodeAt(a-1)<=32;)a-=1;let r=t.slice(n,a).replace(/[\t\n\r]/g,"");if(r===""||e.allowDataImage&&Go.test(r))return!0;let i=/^([a-z][a-z0-9+.-]*):/i.exec(r);return i?Ho.has(i[1].toLowerCase()+":"):!0}function Fr(t){try{return new URL(t,document.baseURI).origin===location.origin}catch{return!1}}var ue=class extends Error{constructor(e,n={},a){super(e,a===void 0?void 0:{cause:a}),this.name="VitrineError",this.code=e,this.params=n}},Vo=new Set(["text/plain","text/markdown","text/x-markdown","application/json","text/json","application/xml","text/xml"]);function $r(t){for(let a of Array.from(t.children)){if(a.hasAttribute("data-json"))continue;let r=qo(a);if(r!==null)return r}let e="";for(let a of Array.from(t.childNodes))a.nodeType===Node.TEXT_NODE||a.nodeType===Node.CDATA_SECTION_NODE?e+=a.nodeValue??"":a.nodeType===Node.ELEMENT_NODE&&!a.hasAttribute("data-json")&&(e+=a.textContent??"");let n=mn(e);return n===""?null:n}function qo(t){if(t instanceof HTMLTemplateElement){let e=t.content.children.length>0;return mn(e?t.innerHTML:t.content.textContent??"")}return t instanceof HTMLScriptElement&&Vo.has(t.type.trim().toLowerCase())?mn(t.textContent??""):null}function jt(t,e){if(t.length>e)throw new ue("tooLarge",{size:t.length,limit:e})}async function fa(t,e){let n=Ko(t),a=Fr(n.href);if(!a&&!e.allowRemote)throw new ue("remoteBlocked");let r=new AbortController,i=setTimeout(()=>r.abort(new ue("timeout")),e.timeout),s=()=>r.abort(e.signal?.reason);e.signal?.addEventListener("abort",s,{once:!0}),e.signal?.aborted&&s();try{let l=await fetch(n.href,{mode:a?"same-origin":"cors",credentials:"same-origin",redirect:"follow",referrerPolicy:"strict-origin-when-cross-origin",signal:r.signal});if(!l.ok)throw new ue("loadFailed",{url:Hr(n),reason:`HTTP ${l.status}`});let c=Number(l.headers.get("content-length"));if(Number.isFinite(c)&&c>e.maxSize*4)throw new ue("tooLarge",{size:c,limit:e.maxSize});return await Wo(l,e.maxSize,r)}catch(l){throw Yo(l,r.signal,n)}finally{clearTimeout(i),e.signal?.removeEventListener("abort",s)}}function Ko(t){let e;try{e=new URL(t.trim(),document.baseURI)}catch{throw new ue("unsafeUrl")}if(e.protocol!=="http:"&&e.protocol!=="https:")throw new ue("unsafeUrl");return e}async function Wo(t,e,n){if(!t.body){let s=await t.text();return jt(s,e),s}let a=t.body.getReader(),r=new TextDecoder,i="";for(;;){let{done:s,value:l}=await a.read();if(s)break;if(i+=r.decode(l,{stream:!0}),i.length>e)throw n.abort(),new ue("tooLarge",{size:`> ${e}`,limit:e})}return i+=r.decode(),jt(i,e),i}function Yo(t,e,n){if(t instanceof ue)return t;if(e.aborted&&e.reason instanceof ue)return e.reason;if(t instanceof DOMException&&t.name==="AbortError")return t;let a=t instanceof Error?t.message:String(t);return new ue("loadFailed",{url:Hr(n),reason:a},t)}function Hr(t){let e=t.origin===location.origin?t.pathname+t.search:t.href;return e.length>120?e.slice(0,119)+"\u2026":e}function ma(t){return t instanceof DOMException&&t.name==="AbortError"}var Zo=1e3,$e=t=>typeof t=="object"&&t!==null&&!Array.isArray(t);function De(t,e=4e3){return typeof t=="number"&&Number.isFinite(t)?String(t):typeof t=="string"?t.trim().slice(0,e):""}function ga(t,e,n){for(let a of e){let r=De(t[a],n);if(r)return r}return""}function Gr(t){let e=De(t,2e3);return e&&jr(e)?e:null}function Lt(t){if(typeof t=="number")return Number.isFinite(t)?t:null;if(typeof t!="string"||!t.trim())return null;let e=Number(t);return Number.isFinite(e)?e:null}function Vr(t,e){let n;try{n=JSON.parse(t)}catch(r){return{ok:!1,error:"json",message:r instanceof Error?r.message:""}}let a=n;return $e(n)&&(a=e.map(r=>n[r]).find(Array.isArray)),Array.isArray(a)?{ok:!0,items:a.filter($e).slice(0,Zo),root:$e(n)?n:{}}:{ok:!1,error:"shape",message:e.map(r=>`"${r}"`).join(", ")}}function qr(t,e){let n=e.replace(/\[(\d+)\]/g,".$1").split(".").map(r=>r.trim()).filter(Boolean),a=t;for(let r of n.slice(0,32))if(Array.isArray(a)&&/^\d+$/.test(r)&&Number(r)<a.length)a=a[Number(r)];else if($e(a)&&Object.hasOwn(a,r))a=a[r];else return{ok:!1};return{ok:!0,value:a}}function Ft(t){return JSON.stringify(t===void 0?null:t,null,2)??"null"}function Kr(t,{keys:e,attributes:n={},otherwise:a}){if(typeof t=="string")return{content:t};if($e(t)){let r=e.find(i=>typeof t[i]=="string");if(r!==void 0){let i={};for(let[s,l]of Object.entries(n))Object.hasOwn(t,s)&&!Object.hasOwn(i,l)&&(i[l]=t[s]);return{content:t[r],attributes:i}}}return a?a(t):{content:Ft(t)}}var ie=Object.freeze({READY:"vt-ready",COPY:"vt-copy",SEARCH:"vt-search",TAB_CHANGE:"vt-tab-change",INPUT:"vt-input",CHANGE:"vt-change",MODE_CHANGE:"vt-mode-change",TAG_ADD:"vt-tag-add",TAG_REMOVE:"vt-tag-remove",TAG_CREATE:"vt-tag-create",TAG_CLICK:"vt-tag-click",SORT:"vt-sort",FULLSCREEN_CHANGE:"vt-fullscreen-change",LAYOUT_CHANGE:"vt-layout-change",SELECT:"vt-select",TOGGLE:"vt-toggle",FILTER_CHANGE:"vt-filter-change",TYPING_END:"vt-typing-end",CHANGE_NAVIGATE:"vt-change-navigate",STEP_TOGGLE:"vt-step-toggle",JOB_CHANGE:"vt-job-change",MATCH:"vt-match",BULK_ACTION:"vt-bulk-action",CELL_EDIT:"vt-cell-edit",COLUMN_CHANGE:"vt-column-change",ROW_ACTIVATE:"vt-row-activate",STATUS_CHANGE:"vt-status-change",DATE_CHANGE:"vt-date-change",EVENT_SELECT:"vt-event-select",PRICING_CHANGE:"vt-pricing-change",PLAN_SELECT:"vt-plan-select",TASK_ADD:"vt-task-add",TASK_MOVE:"vt-task-move",TASK_EDIT:"vt-task-edit",TASK_DELETE:"vt-task-delete",COUNTDOWN_END:"vt-countdown-end",FILE_ADD:"vt-file-add",FILE_REMOVE:"vt-file-remove",UPLOAD_START:"vt-upload-start",UPLOAD_PROGRESS:"vt-upload-progress",UPLOAD_DONE:"vt-upload-done",UPLOAD_ERROR:"vt-upload-error",DOWNLOAD:"vt-download",GENERATE:"vt-generate",BREACH:"vt-breach",ROTATE:"vt-rotate",CONSENT:"vt-consent",HASH:"vt-hash",VERIFY:"vt-verify",LOADING_START:"vt-loading-start",LOADING_END:"vt-loading-end",PROGRESS:"vt-progress",COMPLETE:"vt-complete",CANCEL:"vt-cancel",ERROR:"vt-error"});function oe(t,e,n){return t.dispatchEvent(new CustomEvent(e,{detail:n,bubbles:!0,composed:!0,cancelable:!0}))}var Yr=Object.freeze({copy:"Copy",copyCode:"Copy code",copied:"Copied",copyFailed:"Copy failed",copySource:"Copy source",download:"Download",search:"Search",searchPlaceholder:"Search\u2026",searchNext:"Next match",searchPrevious:"Previous match",searchClose:"Close search",searchCount:"{current} / {total}",searchCountCapped:"{current} / {total}+",searchNone:"No matches",searchResults:"{total} matches",wrap:"Toggle line wrap",showMore:"Show all {count} lines",preview:"Preview",source:"Source",split:"Split",swapPanes:"Swap panes",stackPanes:"Stack panes",syncScroll:"Sync scrolling",tabs:"View",actions:"Actions",toc:"Table of contents",anchor:"Link to this section",table:"Table",tree:"Tree",raw:"Raw",expandAll:"Expand all",collapseAll:"Collapse all",copyPath:"Copy path",copyValue:"Copy value",items:"{count} items",item:"1 item",keys:"{count} keys",key:"1 key",showMoreItems:"Show {count} more",showFullString:"Show full string ({count} characters)",truncated:"Partially expanded: too many nodes.",loading:"Loading\u2026",errorTitle:"Unable to display content",invalidJson:"Invalid JSON at line {line}, column {column}: {message}.",invalidJsonRaw:"Invalid JSON at line {line}, column {column} \u2014 showing raw text.",empty:"Nothing to display",tooLarge:"Content is too large ({size} characters, limit {limit}).",jsonInvalid:"This JSON could not be read: {message}",jsonPathMissing:'Nothing was found at "{path}" in this JSON.',jsonUnusable:"This data cannot be shown by this element.",dataNoList:"Expected a list, or an object with a list under {keys}.",tooDeep:"Nesting is too deep (limit {limit}).",tooComplex:"This document is nested too deeply to display.",unserializable:"This value cannot be converted to JSON (circular reference or BigInt).",highlightSkipped:"Content is large: syntax highlighting is disabled.",loadFailed:'Could not load "{url}": {reason}',remoteBlocked:'Cross-origin URL blocked. Add the "allow-remote" attribute to allow it.',unsafeUrl:"URL blocked: only http(s) URLs can be loaded.",timeout:"Request timed out.",added:"Added",removed:"Removed",code:"Code",edit:"Edit",splitView:"Side by side",unifiedView:"Unified",diffStats:"+{added} \u2212{removed}",diffSimplified:"Many changes: the comparison is simplified to removed and added blocks.",noDifferences:"No differences",previousChange:"Previous change",nextChange:"Next change",changePosition:"{current} of {total}",changeTotal:"{count} changes",terminal:"Terminal",command:"Command",copyCommand:"Copy command",copyCommands:"Copy commands",replay:"Replay",showMoreLines:"Show {count} more lines",files:"Files",copyTree:"Copy tree",treeStats:"{folders} folders, {files} files",invalidTree:"This tree could not be read: {message}",treeTruncated:"Only the first {limit} entries are shown.",status_added:"added",status_removed:"removed",status_modified:"modified",status_highlighted:"highlighted",httpExchange:"Exchange",httpRequest:"Request",httpResponse:"Response",httpBody:"Body",httpHeaders:"Headers",httpQuery:"Query",httpNone:"None",httpNoBody:"No body",httpConnection:"Connection",httpEntry:"Entry",httpEntryPrevious:"Previous entry",httpEntryNext:"Next entry",httpEntryCount:"{index} of {total}",httpServerIp:"Server IP",httpVersion:"HTTP version",httpMimeType:"MIME type",httpBodySize:"Body size (on the wire)",httpContentSize:"Content size (decoded)",httpTransferSize:"Transfer size",httpTlsProtocol:"TLS protocol",httpTlsCipher:"Cipher",httpTlsSubject:"Certificate subject",httpTlsSans:"Alternative names",httpTlsIssuer:"Issuer",httpTlsValidFrom:"Valid from",httpTlsValidTo:"Valid to",httpTlsExpired:"expired",httpBinary:"Binary content ({type})",httpImage:"Response image ({type})",copyUrl:"Copy URL",codeLanguage:"Language",showSecrets:"Show secrets",hideSecrets:"Hide secrets",secretsShown:"Secrets shown",secretsHidden:"Secrets hidden",secretsInCode:"Credentials are masked in this code. Replace them with your own.",invalidHttp:"This HTTP message could not be read: {message}",log:"Log",followLog:"Follow new lines",levelToggle:"Show or hide {level} entries",logNoMatch:"No entry matches the filters.",chartView:"Chart",legend:"Legend",seriesToggle:"Show or hide {name}",copyData:"Copy data",chartSummary:"{type} with {series} series and {points} points.",chartRange:"{name} from {min} to {max}",chart_line:"Line chart",chart_area:"Area chart",chart_bar:"Bar chart",chart_pie:"Donut chart",chartError:"This data could not be charted: {message}",chartTruncated:"Only the first 5,000 points of each series are shown.",chartLoadFailed:"The chart library could not be loaded: {message}",openapiInvalid:"This API description could not be read: {message}",openapiYamlFailed:"The YAML reader could not be loaded: {message}",openapiTruncated:"Only the first 2,000 endpoints are shown.",openapiServers:"Servers",openapiAuth:"Authentication",openapiEndpoints:"Endpoints",openapiTags:"Tags",openapiAllTags:"All",openapiNoMatch:"No endpoint matches.",openapiDeprecated:"deprecated",openapiParameters:"Parameters",openapiName:"Name",openapiIn:"In",openapiType:"Type",openapiDescription:"Description",openapiRequired:"required",openapiRequestBody:"Request body",openapiResponses:"Responses",openapiExample:"Example",openapiExampleValue:"Example",unchangedLines:"Show {count} unchanged lines",copyPatch:"Copy patch",changes:"Changes",original:"Original",modified:"Modified",patch:"Patch",tags:"Tags",noTags:"No tags",addTag:"Add a tag",tagPlaceholder:"tag",suggestions:"Suggestions",createTag:'Create "{tag}"',removeTag:"Remove {tag}",tagAdded:"{tag} added",tagRemoved:"{tag} removed",pressAgainToRemove:"Press Backspace again to remove {tag}",tagDuplicate:"{tag} is already selected.",tagDisabled:"{tag} cannot be selected.",tagLimit:"You can select up to {max} tags.",tagNotAllowed:"{tag} is not in the list.",tagTooLong:"{tag} is too long.",tagInvalid:"{tag} is not a valid tag.",tagRefused:"{tag} was refused.",tagsRequired:"Select at least one tag.",tagCount:"{count} tags",tagCountOne:"1 tag",tagCountMax:"{count} / {max} tags",browseTags:"Browse all tags",otherTags:"Other",clearTags:"Remove all tags",filterTags:"Filter tags",tagsFound:"{count} tags",invalidTags:'The tags must be a JSON array, or an object with "value" and "options".',rowsRange:"Rows {from}\u2013{to} of {total}",noRows:"No rows",firstPage:"First page",previousPage:"Previous page",nextPage:"Next page",lastPage:"Last page",sortBy:"Sort by {name}",column:"Column {n}",rowNumber:"Row",csvStatus:"{rows} rows \xD7 {columns} columns",csvUnclosed:"Unclosed quote starting at line {line}.",tooManyColumns:"Only the first {limit} columns are shown.",matchingRows:"{count} matching rows",undo:"Undo",redo:"Redo",fullscreen:"Full screen",exitFullscreen:"Exit full screen",stopEditing:"Stop editing",editor:"Editor",validJson:"Valid JSON"}),Jo=Object.freeze({copy:"Copier",copyCode:"Copier le code",copied:"Copi\xE9",copyFailed:"\xC9chec de la copie",copySource:"Copier la source",download:"T\xE9l\xE9charger",search:"Rechercher",searchPlaceholder:"Rechercher\u2026",searchNext:"R\xE9sultat suivant",searchPrevious:"R\xE9sultat pr\xE9c\xE9dent",searchClose:"Fermer la recherche",searchCount:"{current} / {total}",searchCountCapped:"{current} / {total}+",searchNone:"Aucun r\xE9sultat",searchResults:"{total} r\xE9sultats",wrap:"Activer/d\xE9sactiver le retour \xE0 la ligne",showMore:"Afficher les {count} lignes",preview:"Aper\xE7u",source:"Source",split:"C\xF4te \xE0 c\xF4te",swapPanes:"Inverser les panneaux",stackPanes:"Empiler les panneaux",syncScroll:"Synchroniser le d\xE9filement",tabs:"Affichage",actions:"Actions",toc:"Table des mati\xE8res",anchor:"Lien vers cette section",table:"Tableau",tree:"Arbre",raw:"Brut",expandAll:"Tout d\xE9plier",collapseAll:"Tout replier",copyPath:"Copier le chemin",copyValue:"Copier la valeur",items:"{count} \xE9l\xE9ments",item:"1 \xE9l\xE9ment",keys:"{count} cl\xE9s",key:"1 cl\xE9",showMoreItems:"Afficher {count} de plus",showFullString:"Afficher toute la cha\xEEne ({count} caract\xE8res)",truncated:"D\xE9pliage partiel : trop de n\u0153uds.",loading:"Chargement\u2026",errorTitle:"Impossible d\u2019afficher le contenu",invalidJson:"JSON invalide \xE0 la ligne {line}, colonne {column} : {message}.",invalidJsonRaw:"JSON invalide \xE0 la ligne {line}, colonne {column} \u2014 affichage du texte brut.",empty:"Rien \xE0 afficher",tooLarge:"Contenu trop volumineux ({size} caract\xE8res, limite {limit}).",jsonInvalid:"Ce JSON n'a pas pu \xEAtre lu : {message}",jsonPathMissing:"Rien n\u2019a \xE9t\xE9 trouv\xE9 \xE0 \xAB {path} \xBB dans ce JSON.",jsonUnusable:"Ces donn\xE9es ne peuvent pas \xEAtre affich\xE9es par cet \xE9l\xE9ment.",dataNoList:"Une liste \xE9tait attendue, ou un objet avec une liste sous {keys}.",tooDeep:"Imbrication trop profonde (limite {limit}).",tooComplex:"Ce document est trop imbriqu\xE9 pour \xEAtre affich\xE9.",unserializable:"Cette valeur ne peut pas \xEAtre convertie en JSON (r\xE9f\xE9rence circulaire ou BigInt).",highlightSkipped:"Contenu volumineux : coloration syntaxique d\xE9sactiv\xE9e.",loadFailed:"Impossible de charger \xAB {url} \xBB : {reason}",remoteBlocked:"URL d\u2019une autre origine bloqu\xE9e. Ajoutez l\u2019attribut \xAB allow-remote \xBB pour l\u2019autoriser.",unsafeUrl:"URL bloqu\xE9e : seules les URL http(s) peuvent \xEAtre charg\xE9es.",timeout:"D\xE9lai de la requ\xEAte d\xE9pass\xE9.",added:"Ajout\xE9",removed:"Supprim\xE9",code:"Code",edit:"Modifier",splitView:"C\xF4te \xE0 c\xF4te",unifiedView:"Unifi\xE9",diffStats:"+{added} \u2212{removed}",diffSimplified:"Beaucoup de changements : la comparaison est simplifi\xE9e en blocs retir\xE9s et ajout\xE9s.",noDifferences:"Aucune diff\xE9rence",previousChange:"Modification pr\xE9c\xE9dente",nextChange:"Modification suivante",changePosition:"{current} sur {total}",changeTotal:"Modifications : {count}",terminal:"Terminal",command:"Commande",copyCommand:"Copier la commande",copyCommands:"Copier les commandes",replay:"Rejouer",showMoreLines:"Afficher {count} lignes de plus",files:"Fichiers",copyTree:"Copier l'arborescence",treeStats:"{folders} dossiers, {files} fichiers",invalidTree:"Impossible de lire cette arborescence : {message}",treeTruncated:"Seules les {limit} premi\xE8res entr\xE9es sont affich\xE9es.",status_added:"ajout\xE9",status_removed:"supprim\xE9",status_modified:"modifi\xE9",status_highlighted:"mis en \xE9vidence",httpExchange:"\xC9change",httpRequest:"Requ\xEAte",httpResponse:"R\xE9ponse",httpBody:"Corps",httpHeaders:"En-t\xEAtes",httpQuery:"Param\xE8tres",httpNone:"Aucun",httpNoBody:"Pas de corps",httpConnection:"Connexion",httpEntry:"Entr\xE9e",httpEntryPrevious:"Entr\xE9e pr\xE9c\xE9dente",httpEntryNext:"Entr\xE9e suivante",httpEntryCount:"{index} sur {total}",httpServerIp:"IP du serveur",httpVersion:"Version HTTP",httpMimeType:"Type MIME",httpBodySize:"Taille du corps (transmise)",httpContentSize:"Taille du contenu (d\xE9cod\xE9)",httpTransferSize:"Taille transf\xE9r\xE9e",httpTlsProtocol:"Protocole TLS",httpTlsCipher:"Chiffrement",httpTlsSubject:"Sujet du certificat",httpTlsSans:"Noms alternatifs",httpTlsIssuer:"\xC9metteur",httpTlsValidFrom:"Valide \xE0 partir du",httpTlsValidTo:"Valide jusqu\u2019au",httpTlsExpired:"expir\xE9",httpBinary:"Contenu binaire ({type})",httpImage:"Image de la r\xE9ponse ({type})",copyUrl:"Copier l'URL",codeLanguage:"Langage",showSecrets:"Afficher les secrets",hideSecrets:"Masquer les secrets",secretsShown:"Secrets affich\xE9s",secretsHidden:"Secrets masqu\xE9s",secretsInCode:"Les identifiants sont masqu\xE9s dans ce code. Remplacez-les par les v\xF4tres.",invalidHttp:"Impossible de lire ce message HTTP : {message}",log:"Journal",followLog:"Suivre les nouvelles lignes",levelToggle:"Afficher ou masquer les entr\xE9es {level}",logNoMatch:"Aucune entr\xE9e ne correspond aux filtres.",chartView:"Graphique",legend:"L\xE9gende",seriesToggle:"Afficher ou masquer {name}",copyData:"Copier les donn\xE9es",chartSummary:"{type} avec {series} s\xE9ries et {points} points.",chartRange:"{name} de {min} \xE0 {max}",chart_line:"Graphique en courbes",chart_area:"Graphique en aires",chart_bar:"Graphique en barres",chart_pie:"Graphique en anneau",chartError:"Impossible de tracer ces donn\xE9es : {message}",chartTruncated:"Seuls les 5 000 premiers points de chaque s\xE9rie sont affich\xE9s.",chartLoadFailed:"Impossible de charger la biblioth\xE8que de graphiques : {message}",openapiInvalid:"Impossible de lire cette description d\u2019API : {message}",openapiYamlFailed:"Impossible de charger le lecteur YAML : {message}",openapiTruncated:"Seuls les 2 000 premiers points d\u2019acc\xE8s sont affich\xE9s.",openapiServers:"Serveurs",openapiAuth:"Authentification",openapiEndpoints:"Points d\u2019acc\xE8s",openapiTags:"Tags",openapiAllTags:"Tous",openapiNoMatch:"Aucun point d\u2019acc\xE8s ne correspond.",openapiDeprecated:"obsol\xE8te",openapiParameters:"Param\xE8tres",openapiName:"Nom",openapiIn:"Emplacement",openapiType:"Type",openapiDescription:"Description",openapiRequired:"requis",openapiRequestBody:"Corps de la requ\xEAte",openapiResponses:"R\xE9ponses",openapiExample:"Exemple",openapiExampleValue:"Exemple",unchangedLines:"Afficher {count} lignes inchang\xE9es",copyPatch:"Copier le patch",changes:"Modifications",original:"Original",modified:"Modifi\xE9",patch:"Patch",tags:"Tags",noTags:"Aucun tag",addTag:"Ajouter un tag",tagPlaceholder:"tag",suggestions:"Suggestions",createTag:"Cr\xE9er \xAB {tag} \xBB",removeTag:"Retirer {tag}",tagAdded:"{tag} ajout\xE9",tagRemoved:"{tag} retir\xE9",pressAgainToRemove:"Appuyez de nouveau sur Retour arri\xE8re pour retirer {tag}",tagDuplicate:"{tag} est d\xE9j\xE0 s\xE9lectionn\xE9.",tagDisabled:"{tag} ne peut pas \xEAtre s\xE9lectionn\xE9.",tagLimit:"Vous pouvez s\xE9lectionner jusqu\u2019\xE0 {max} tags.",tagNotAllowed:"{tag} n\u2019est pas dans la liste.",tagTooLong:"{tag} est trop long.",tagInvalid:"{tag} n\u2019est pas un tag valide.",tagRefused:"{tag} a \xE9t\xE9 refus\xE9.",tagsRequired:"S\xE9lectionnez au moins un tag.",tagCount:"{count} tags",tagCountOne:"1 tag",tagCountMax:"{count} / {max} tags",browseTags:"Parcourir tous les tags",otherTags:"Autres",clearTags:"Retirer tous les tags",filterTags:"Filtrer les tags",tagsFound:"{count} tags",invalidTags:"Les tags doivent \xEAtre un tableau JSON, ou un objet avec \xAB value \xBB et \xAB options \xBB.",rowsRange:"Lignes {from}\u2013{to} sur {total}",noRows:"Aucune ligne",firstPage:"Premi\xE8re page",previousPage:"Page pr\xE9c\xE9dente",nextPage:"Page suivante",lastPage:"Derni\xE8re page",sortBy:"Trier par {name}",column:"Colonne {n}",rowNumber:"Ligne",csvStatus:"{rows} lignes \xD7 {columns} colonnes",csvUnclosed:"Guillemet non ferm\xE9 \xE0 partir de la ligne {line}.",tooManyColumns:"Seules les {limit} premi\xE8res colonnes sont affich\xE9es.",matchingRows:"{count} lignes correspondantes",undo:"Annuler",redo:"R\xE9tablir",fullscreen:"Plein \xE9cran",exitFullscreen:"Quitter le plein \xE9cran",stopEditing:"Terminer la modification",editor:"\xC9diteur",validJson:"JSON valide"}),Zr={},gn=new Map;function bn(t){for(let[e,n]of Object.entries(t))e==="en"?Object.assign(Zr,n):gn.set(e,{...gn.get(e)??{},...n});for(let e of ba)e()}var Wr=new Map([["en",Yr],["fr",Jo]]);var ba=new Set;function Jr(t){return ba.add(t),()=>ba.delete(t)}function ya(t){let e=Wr.get(t),n=Wr.get(String(t).split("-")[0]);return(a,r)=>{let i=String(t).split("-")[0],s=e?.[a]??n?.[a]??gn.get(t)?.[a]??gn.get(i)?.[a]??Yr[a]??Zr[a]??String(a);return r?s.replace(/\{(\w+)\}/g,(l,c)=>Object.prototype.hasOwnProperty.call(r,c)?String(r[c]):l):s}}function yn(t,e){try{return new Intl.NumberFormat(e).format(t)}catch{return String(t)}}var Xr=`/* Vitrine Light \u2014 default light theme. Values: docs/DESIGN_SYSTEM.md \xA72. */
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
`;var Qr=`/* Vitrine Dark \u2014 default dark theme. Values: docs/DESIGN_SYSTEM.md \xA72. */
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
`;var es=`/* Vitrine Dim \u2014 softer, blue-grey dark theme for long reading sessions. */
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
`;var ts=`/* Vitrine Paper \u2014 warm, low-glare light theme. */
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
`;var ns=`/* Vitrine High Contrast \u2014 maximum legibility (WCAG AAA text contrast). */
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
`;var ad=Object.freeze(["bg","surface","surface-sunken","surface-raised","border","border-strong","fg","fg-muted","accent","accent-fg","on-accent","accent-soft","highlight","highlight-current","line-highlight","success","warning","danger","info","diff-added","diff-removed","shadow","syntax-keyword","syntax-string","syntax-number","syntax-function","syntax-type","syntax-comment","syntax-attr","syntax-tag","syntax-meta"]),ct=new Map,lt=new CSSStyleSheet;function al(t){let e=/\[data-theme='([a-z0-9-]+)'\]/.exec(t)?.[1];if(!e)throw new Error("[vitrine] Theme file without a [data-theme] selector.");let n=/color-scheme:\s*(light|dark)\s*;/.exec(t)?.[1]==="dark"?"dark":"light",a={};for(let[,r,i]of t.matchAll(/--vt-([a-z0-9-]+)\s*:\s*([^;]+);/g))a[r]=i.trim();return{name:e,definition:{colorScheme:n,tokens:a}}}for(let t of[Xr,Qr,es,ts,ns]){let{name:e,definition:n}=al(t);ct.set(e,n)}var rd=Object.freeze([...ct.keys()]);function as(t){let e=ct.get(t);return e?{colorScheme:e.colorScheme,tokens:{...e.tokens}}:void 0}function rl(){for(;lt.cssRules.length;)lt.deleteRule(0);for(let[t,e]of ct){let n=lt.insertRule(`.vt[data-theme="${t}"] {}`,lt.cssRules.length),a=lt.cssRules[n].style;a.setProperty("color-scheme",e.colorScheme);for(let[r,i]of Object.entries(e.tokens))a.setProperty(`--_${r}`,`var(--vt-${r}, ${i})`)}}rl();var va=typeof matchMedia=="function"?matchMedia("(prefers-color-scheme: dark)"):null,xa=new Set;function sl(){for(let t of xa)t()}va?.addEventListener?.("change",sl);function rs(t){return xa.add(t),()=>xa.delete(t)}function ss(t){let e=J(),n=t?.trim().toLowerCase()||e.theme;if(n!=="auto"&&!ct.has(n)&&(n=ct.has(e.theme)?e.theme:"auto"),n!=="auto")return n;let a=va?.matches?e.darkTheme:e.lightTheme;return ct.has(a)?a:va?.matches?"dark":"light"}var il="",ol="",ll="";function is(){return il}function os(){return ll}function ls(){return ol}var cs=Object.freeze({"1c-light":0,"a11y-dark":1,"a11y-light":0,agate:1,"an-old-hope":1,androidstudio:1,"arduino-light":0,arta:1,ascetic:0,"atom-one-dark":1,"atom-one-dark-reasonable":1,"atom-one-light":0,"base16-3024":1,"base16-apathy":1,"base16-apprentice":1,"base16-ashes":1,"base16-atelier-cave":1,"base16-atelier-cave-light":0,"base16-atelier-dune":1,"base16-atelier-dune-light":0,"base16-atelier-estuary":1,"base16-atelier-estuary-light":0,"base16-atelier-forest":1,"base16-atelier-forest-light":0,"base16-atelier-heath":1,"base16-atelier-heath-light":0,"base16-atelier-lakeside":1,"base16-atelier-lakeside-light":0,"base16-atelier-plateau":1,"base16-atelier-plateau-light":0,"base16-atelier-savanna":1,"base16-atelier-savanna-light":0,"base16-atelier-seaside":1,"base16-atelier-seaside-light":0,"base16-atelier-sulphurpool":1,"base16-atelier-sulphurpool-light":0,"base16-atlas":1,"base16-bespin":1,"base16-black-metal":1,"base16-black-metal-bathory":1,"base16-black-metal-burzum":1,"base16-black-metal-dark-funeral":1,"base16-black-metal-gorgoroth":1,"base16-black-metal-immortal":1,"base16-black-metal-khold":1,"base16-black-metal-marduk":1,"base16-black-metal-mayhem":1,"base16-black-metal-nile":1,"base16-black-metal-venom":1,"base16-brewer":1,"base16-bright":1,"base16-brogrammer":1,"base16-brush-trees":0,"base16-brush-trees-dark":1,"base16-chalk":1,"base16-circus":1,"base16-classic-dark":1,"base16-classic-light":0,"base16-codeschool":1,"base16-colors":1,"base16-cupcake":0,"base16-cupertino":0,"base16-danqing":1,"base16-darcula":1,"base16-dark-violet":1,"base16-darkmoss":1,"base16-darktooth":1,"base16-decaf":1,"base16-default-dark":1,"base16-default-light":0,"base16-dirtysea":0,"base16-dracula":1,"base16-edge-dark":1,"base16-edge-light":0,"base16-eighties":1,"base16-embers":1,"base16-equilibrium-dark":1,"base16-equilibrium-gray-dark":1,"base16-equilibrium-gray-light":0,"base16-equilibrium-light":0,"base16-espresso":1,"base16-eva":1,"base16-eva-dim":1,"base16-flat":1,"base16-framer":1,"base16-fruit-soda":0,"base16-gigavolt":1,"base16-github":0,"base16-google-dark":1,"base16-google-light":0,"base16-grayscale-dark":1,"base16-grayscale-light":0,"base16-green-screen":1,"base16-gruvbox-dark-hard":1,"base16-gruvbox-dark-medium":1,"base16-gruvbox-dark-pale":1,"base16-gruvbox-dark-soft":1,"base16-gruvbox-light-hard":0,"base16-gruvbox-light-medium":0,"base16-gruvbox-light-soft":0,"base16-hardcore":1,"base16-harmonic16-dark":1,"base16-harmonic16-light":0,"base16-heetch-dark":1,"base16-heetch-light":0,"base16-helios":1,"base16-hopscotch":1,"base16-horizon-dark":1,"base16-horizon-light":0,"base16-humanoid-dark":1,"base16-humanoid-light":0,"base16-ia-dark":1,"base16-ia-light":0,"base16-icy-dark":1,"base16-ir-black":1,"base16-isotope":1,"base16-kimber":1,"base16-london-tube":1,"base16-macintosh":1,"base16-marrakesh":1,"base16-materia":1,"base16-material":1,"base16-material-darker":1,"base16-material-lighter":0,"base16-material-palenight":1,"base16-material-vivid":1,"base16-mellow-purple":1,"base16-mexico-light":0,"base16-mocha":1,"base16-monokai":1,"base16-nebula":1,"base16-nord":1,"base16-nova":1,"base16-ocean":1,"base16-oceanicnext":1,"base16-one-light":0,"base16-onedark":1,"base16-outrun-dark":1,"base16-papercolor-dark":1,"base16-papercolor-light":0,"base16-paraiso":1,"base16-pasque":1,"base16-phd":1,"base16-pico":1,"base16-pop":1,"base16-porple":1,"base16-qualia":1,"base16-railscasts":1,"base16-rebecca":1,"base16-ros-pine":1,"base16-ros-pine-dawn":0,"base16-ros-pine-moon":1,"base16-sagelight":0,"base16-sandcastle":1,"base16-seti-ui":1,"base16-shapeshifter":0,"base16-silk-dark":1,"base16-silk-light":0,"base16-snazzy":1,"base16-solar-flare":1,"base16-solar-flare-light":0,"base16-solarized-dark":1,"base16-solarized-light":0,"base16-spacemacs":1,"base16-summercamp":1,"base16-summerfruit-dark":1,"base16-summerfruit-light":0,"base16-synth-midnight-terminal-dark":1,"base16-synth-midnight-terminal-light":0,"base16-tango":1,"base16-tender":1,"base16-tomorrow":0,"base16-tomorrow-night":1,"base16-twilight":1,"base16-unikitty-dark":1,"base16-unikitty-light":0,"base16-vulcan":1,"base16-windows-10":1,"base16-windows-10-light":0,"base16-windows-95":1,"base16-windows-95-light":0,"base16-windows-high-contrast":1,"base16-windows-high-contrast-light":0,"base16-windows-nt":1,"base16-windows-nt-light":0,"base16-woodland":1,"base16-xcode-dusk":1,"base16-zenburn":1,"brown-paper":0,"codepen-embed":1,"color-brewer":0,"cybertopia-cherry":0,"cybertopia-dimmer":0,"cybertopia-icecap":0,"cybertopia-saturated":0,dark:1,default:0,devibeans:1,docco:0,equinox:0,far:1,felipec:1,foundation:0,github:0,"github-dark":1,"github-dark-dimmed":1,gml:1,googlecode:0,"gradient-dark":1,"gradient-light":0,grayscale:0,hybrid:1,idea:0,"intellij-light":0,"ir-black":1,"isbl-editor-dark":1,"isbl-editor-light":0,"kimbie-dark":1,"kimbie-light":0,lightfair:0,lioshi:1,magula:0,"mono-blue":0,monokai:1,"monokai-sublime":1,"night-owl":1,"nnfx-dark":1,"nnfx-light":0,nord:1,obsidian:1,"panda-syntax-dark":1,"panda-syntax-light":0,"paraiso-dark":1,"paraiso-light":0,pojoaque:0,purebasic:0,"qtcreator-dark":1,"qtcreator-light":0,rainbow:1,"rose-pine":1,"rose-pine-dawn":0,"rose-pine-moon":1,routeros:0,"school-book":0,"shades-of-purple":1,srcery:1,"stackoverflow-dark":1,"stackoverflow-light":0,sunburst:1,"tokyo-night-dark":1,"tokyo-night-light":0,"tomorrow-night-blue":1,"tomorrow-night-bright":1,vs:0,"vs-dark":1,vs2015:1,xcode:0,xt256:1});var _a=new Map,us=new Map;function ds(t){if(typeof t!="string")return null;let e=t.trim().toLowerCase().replace(/\//g,"-");return!e||e.length>60?null:Object.prototype.hasOwnProperty.call(cs,e)?e:null}function ps(t){return us.get(t)}function hs(t){let e=_a.get(t);if(e)return e;let n=cl(t);return _a.set(t,n),n}async function cl(t){let e=J().syntaxThemesUrl||ls();if(!e)return null;try{let n=new URL(`${t}.css`,new URL(e.endsWith("/")?e:`${e}/`,document.baseURI));if(n.protocol!=="https:"&&n.protocol!=="http:")return null;let a=await fetch(n.href,{credentials:"same-origin"});if(!a.ok)throw new Error(`HTTP ${a.status}`);let r=await a.text(),i=new CSSStyleSheet;return i.replaceSync(r),us.set(t,i),i}catch(n){return console.warn(`[vitrine] Could not load the "${t}" syntax theme.`,n),_a.delete(t),null}}var fs="http://www.w3.org/2000/svg";var $t=["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"}],Ht=["path",{d:"M14 2v4a2 2 0 0 0 2 2h4"}],ul={copy:[["rect",{width:"14",height:"14",x:"8",y:"8",rx:"2",ry:"2"}],["path",{d:"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"}]],check:[["path",{d:"M20 6 9 17l-5-5"}]],search:[["path",{d:"m21 21-4.34-4.34"}],["circle",{cx:"11",cy:"11",r:"8"}]],"chevron-up":[["path",{d:"m18 15-6-6-6 6"}]],"chevron-down":[["path",{d:"m6 9 6 6 6-6"}]],"chevron-right":[["path",{d:"m9 18 6-6-6-6"}]],wrap:[["path",{d:"m16 16-3 3 3 3"}],["path",{d:"M3 12h14.5a1 1 0 0 1 0 7H13"}],["path",{d:"M3 19h6"}],["path",{d:"M3 5h18"}]],download:[["path",{d:"M12 15V3"}],["path",{d:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"}],["path",{d:"m7 10 5 5 5-5"}]],"expand-all":[["path",{d:"m7 15 5 5 5-5"}],["path",{d:"m7 9 5-5 5 5"}]],"collapse-all":[["path",{d:"m7 20 5-5 5 5"}],["path",{d:"m7 4 5 5 5-5"}]],link:[["path",{d:"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"}],["path",{d:"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"}]],eye:[["path",{d:"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"}],["circle",{cx:"12",cy:"12",r:"3"}]],code:[["path",{d:"m16 18 6-6-6-6"}],["path",{d:"m8 6-6 6 6 6"}]],columns:[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M12 3v18"}]],list:[["path",{d:"M3 5h.01"}],["path",{d:"M3 12h.01"}],["path",{d:"M3 19h.01"}],["path",{d:"M8 5h13"}],["path",{d:"M8 12h13"}],["path",{d:"M8 19h13"}]],pencil:[["path",{d:"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"}],["path",{d:"m15 5 4 4"}]],"chevron-left":[["path",{d:"m15 18-6-6 6-6"}]],"chevrons-left":[["path",{d:"m11 17-5-5 5-5"}],["path",{d:"m18 17-5-5 5-5"}]],"chevrons-right":[["path",{d:"m6 17 5-5-5-5"}],["path",{d:"m13 17 5-5-5-5"}]],sort:[["path",{d:"m21 16-4 4-4-4"}],["path",{d:"M17 20V4"}],["path",{d:"m3 8 4-4 4 4"}],["path",{d:"M7 4v16"}]],"sort-up":[["path",{d:"m5 12 7-7 7 7"}],["path",{d:"M12 19V5"}]],"sort-down":[["path",{d:"M12 5v14"}],["path",{d:"m19 12-7 7-7-7"}]],table:[["path",{d:"M12 3v18"}],["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M3 9h18"}],["path",{d:"M3 15h18"}]],undo:[["path",{d:"M9 14 4 9l5-5"}],["path",{d:"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"}]],redo:[["path",{d:"m15 14 5-5-5-5"}],["path",{d:"M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"}]],maximize:[["path",{d:"M15 3h6v6"}],["path",{d:"m21 3-7 7"}],["path",{d:"m3 21 7-7"}],["path",{d:"M9 21H3v-6"}]],minimize:[["path",{d:"m14 10 7-7"}],["path",{d:"M20 10h-6V4"}],["path",{d:"m3 21 7-7"}],["path",{d:"M4 14h6v6"}]],swap:[["path",{d:"M8 3 4 7l4 4"}],["path",{d:"M4 7h16"}],["path",{d:"m16 21 4-4-4-4"}],["path",{d:"M20 17H4"}]],filter:[["path",{d:"M22 3H2l8 9.46V19l4 2v-8.54L22 3z"}]],keyboard:[["rect",{width:"20",height:"16",x:"2",y:"4",rx:"2"}],["path",{d:"M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"}]],rows:[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2"}],["path",{d:"M3 12h18"}]],"sync-scroll":[["path",{d:"M9 17H7A5 5 0 0 1 7 7h2"}],["path",{d:"M15 7h2a5 5 0 1 1 0 10h-2"}],["line",{x1:"8",x2:"16",y1:"12",y2:"12"}]],alert:[["path",{d:"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"}],["path",{d:"M12 9v4"}],["path",{d:"M12 17h.01"}]],close:[["path",{d:"M18 6 6 18"}],["path",{d:"m6 6 12 12"}]],replay:[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"}],["path",{d:"M3 3v5h5"}]],chart:[["path",{d:"M3 3v16a2 2 0 0 0 2 2h16"}],["path",{d:"m19 9-5 5-4-4-3 3"}]],follow:[["path",{d:"M12 17V3"}],["path",{d:"m6 11 6 6 6-6"}],["path",{d:"M19 21H5"}]],terminal:[["path",{d:"M12 19h8"}],["path",{d:"m4 17 6-6-6-6"}]],folder:[["path",{d:"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"}]],"folder-open":[["path",{d:"m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"}]],file:[$t,Ht],"file-code":[$t,Ht,["path",{d:"m10 13-2 2 2 2"}],["path",{d:"m14 17 2-2-2-2"}]],"file-text":[$t,Ht,["path",{d:"M10 9H8"}],["path",{d:"M16 13H8"}],["path",{d:"M16 17H8"}]],"file-image":[$t,Ht,["circle",{cx:"10",cy:"12",r:"2"}],["path",{d:"m20 17-1.296-1.296a2.41 2.41 0 0 0-3.408 0L9 22"}]],"file-data":[$t,Ht,["path",{d:"M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"}],["path",{d:"M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1"}]],lock:[["rect",{width:"18",height:"11",x:"3",y:"11",rx:"2",ry:"2"}],["path",{d:"M7 11V7a5 5 0 0 1 10 0v4"}]],"eye-off":[["path",{d:"M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"}],["path",{d:"M14.084 14.158a3 3 0 0 1-4.242-4.242"}],["path",{d:"M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"}],["path",{d:"m2 2 20 20"}]],"status-circle":[["circle",{cx:"12",cy:"12",r:"9"}]],"status-running":[["path",{d:"M21 12a9 9 0 1 1-6.22-8.56"}]],"status-skipped":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m5.7 5.7 12.6 12.6"}]],"status-success":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m8.5 12 2.5 2.5 4.5-5"}]],"status-failure":[["circle",{cx:"12",cy:"12",r:"9"}],["path",{d:"m15 9-6 6"}],["path",{d:"m9 9 6 6"}]],plus:[["path",{d:"M5 12h14"}],["path",{d:"M12 5v14"}]],trash:[["path",{d:"M3 6h18"}],["path",{d:"M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"}],["path",{d:"M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"}]],"dots-vertical":[["circle",{cx:"12",cy:"12",r:"1"}],["circle",{cx:"12",cy:"5",r:"1"}],["circle",{cx:"12",cy:"19",r:"1"}]],upload:[["path",{d:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"}],["path",{d:"m17 8-5-5-5 5"}],["path",{d:"M12 3v12"}]],help:[["circle",{cx:"12",cy:"12",r:"10"}],["path",{d:"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"}],["path",{d:"M12 17h.01"}]],grip:[["circle",{cx:"9",cy:"5",r:"1"}],["circle",{cx:"9",cy:"12",r:"1"}],["circle",{cx:"9",cy:"19",r:"1"}],["circle",{cx:"15",cy:"5",r:"1"}],["circle",{cx:"15",cy:"12",r:"1"}],["circle",{cx:"15",cy:"19",r:"1"}]],calendar:[["rect",{width:"18",height:"18",x:"3",y:"4",rx:"2"}],["path",{d:"M16 2v4"}],["path",{d:"M8 2v4"}],["path",{d:"M3 10h18"}]],user:[["circle",{cx:"12",cy:"8",r:"5"}],["path",{d:"M20 21a8 8 0 0 0-16 0"}]],history:[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"}],["path",{d:"M3 3v5h5"}],["path",{d:"M12 7v5l4 2"}]],"arrow-right":[["path",{d:"M5 12h14"}],["path",{d:"m12 5 7 7-7 7"}]],minus:[["path",{d:"M5 12h14"}]],refresh:[["path",{d:"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"}],["path",{d:"M21 3v5h-5"}],["path",{d:"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"}],["path",{d:"M8 16H3v5"}]],key:[["path",{d:"M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"}],["circle",{cx:"16.5",cy:"7.5",r:".5"}]],"shield-check":[["path",{d:"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{d:"m9 12 2 2 4-4"}]],"shield-alert":[["path",{d:"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{d:"M12 8v4"}],["path",{d:"M12 16h.01"}]],"arrow-up":[["path",{d:"m5 12 7-7 7 7"}],["path",{d:"M12 19V5"}]],star:[["path",{d:"M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"}]],fork:[["circle",{cx:"12",cy:"18",r:"3"}],["circle",{cx:"6",cy:"6",r:"3"}],["circle",{cx:"18",cy:"6",r:"3"}],["path",{d:"M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9"}],["path",{d:"M12 12v3"}]],issue:[["circle",{cx:"12",cy:"12",r:"10"}],["circle",{cx:"12",cy:"12",r:"1"}]],tag:[["path",{d:"M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"}],["circle",{cx:"7.5",cy:"7.5",r:".5"}]],scale:[["path",{d:"m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"}],["path",{d:"m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"}],["path",{d:"M7 21h10"}],["path",{d:"M12 3v18"}],["path",{d:"M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"}]]};function Ue(t){let e=document.createElementNS(fs,"svg");e.setAttribute("viewBox","0 0 24 24"),e.setAttribute("fill","none"),e.setAttribute("stroke","currentColor"),e.setAttribute("stroke-width","2.1"),e.setAttribute("stroke-linecap","round"),e.setAttribute("stroke-linejoin","round"),e.setAttribute("aria-hidden","true"),e.setAttribute("focusable","false"),e.setAttribute("class","icon");for(let[n,a]of ul[t]??[]){let r=document.createElementNS(fs,n);for(let[i,s]of Object.entries(a))r.setAttribute(i,s);e.append(r)}return e}var wa=new WeakMap,Gt=null;function dl(){return Gt||typeof IntersectionObserver>"u"||(Gt=new IntersectionObserver(t=>{for(let e of t)e.isIntersecting&&Ea(e.target)},{rootMargin:"600px 0px"})),Gt}function ms(t,e){wa.set(t,e);let n=dl();n?n.observe(t):Ea(t)}function Ea(t){let e=wa.get(t);e&&(wa.delete(t),Gt?.unobserve(t),e())}function gs(t){for(let e of Array.from(t.querySelectorAll(".chunk[data-pending]")))Ea(e)}var pl=5e3,vn=200;function hl(t){return t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}function fl(t,e,n=pl){let a=[];if(!e)return{starts:a,capped:!1};let r=new RegExp(hl(e),"gi"),i;for(;(i=r.exec(t))!==null;){if(a.length===n)return{starts:a,capped:!0};a.push(i.index),i[0].length===0&&(r.lastIndex+=1)}return{starts:a,capped:!1}}var Vt=class{constructor(e,n={}){this.root=e,this.skip=n.skip??"",this.matches=[],this.current=-1}run(e){this.clear();let n=e.slice(0,vn);if(!n)return{total:0,capped:!1};gs(this.root);let{nodes:a,starts:r,text:i}=this.collectText(),{starts:s,capped:l}=fl(i,n),c=s.map(()=>[]);for(let d=s.length-1;d>=0;d-=1){let p=s[d],x=p+n.length,b=ml(r,x-1);for(;b>=0&&r[b]+(a[b].nodeValue??"").length>p;){let w=r[b],h=Math.max(p,w)-w,y=Math.min(x,w+(a[b].nodeValue??"").length)-w;y>h&&c[d].unshift(gl(a[b],h,y,d)),b-=1}}return this.matches=c,{total:c.length,capped:l}}collectText(){let e=this.skip,n=document.createTreeWalker(this.root,NodeFilter.SHOW_TEXT,{acceptNode(l){let c=l.parentElement;return e&&c&&c.closest(e)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT}}),a=[],r=[],i=[],s=0;for(let l=n.nextNode();l;l=n.nextNode()){let c=l.nodeValue??"";c&&(a.push(l),r.push(s),i.push(c),s+=c.length)}return{nodes:a,starts:r,text:i.join("")}}go(e){if(!this.matches.length)return null;let n=this.matches.length,a=(e%n+n)%n;for(let r of this.matches[this.current]??[])r.classList.remove("current");this.current=a;for(let r of this.matches[a])r.classList.add("current");return this.matches[a][0]??null}unsetCurrent(){for(let e of this.matches[this.current]??[])e.classList.remove("current");this.current=-1}clear(){let e=new Set;for(let n of this.matches)for(let a of n){let r=a.parentNode;r&&(a.replaceWith(...Array.from(a.childNodes)),e.add(r))}for(let n of e)n.normalize();this.matches=[],this.current=-1}};function ml(t,e){let n=0,a=t.length-1;for(;n<a;){let r=n+a+1>>1;t[r]<=e?n=r:a=r-1}return n}function gl(t,e,n,a){let r=t.splitText(e);r.splitText(n-e);let i=document.createElement("mark");return i.className="match",i.setAttribute("part","match"),i.dataset.match=String(a),r.replaceWith(i),i.appendChild(r),i}function de(t){let e=g("button",{class:"btn",part:`button${t.part?` ${t.part}`:""}`,attrs:{type:"button","aria-label":t.label,title:t.label,"aria-pressed":t.pressed===void 0?null:String(t.pressed),"data-focus-key":t.key},on:{click:t.onClick}});return e.append(Ue(t.icon)),e}function ys(t,e,n){let a=t.querySelector("svg");a&&(a.replaceWith(Ue(n?"check":"alert")),t.classList.toggle("done",n),setTimeout(()=>{t.querySelector("svg")?.replaceWith(Ue(e)),t.classList.remove("done")},1500))}var xn=class{constructor(e,n,a=""){this.t=e,this.handlers=n,this.total=0,this.capped=!1,this.index=-1;let r=Ne("search");this.input=g("input",{class:"search-input",part:"search-input",attrs:{id:r,type:"search",placeholder:e("searchPlaceholder"),"aria-label":e("search"),maxlength:vn,autocomplete:"off",spellcheck:"false",enterkeyhint:"search","data-focus-key":"search-input"}}),this.input.value=a.slice(0,vn),this.count=g("span",{class:"search-count",part:"search-count",attrs:{"aria-hidden":"true"}});let i=de({icon:"chevron-up",label:e("searchPrevious"),onClick:()=>this.step(-1),key:"search-prev"}),s=de({icon:"chevron-down",label:e("searchNext"),onClick:()=>this.step(1),key:"search-next"}),l=de({icon:"close",label:e("searchClose"),onClick:()=>n.onClose(),key:"search-close"});this.element=g("div",{class:"search",part:"search",attrs:{role:"search"}},this.input,this.count,i,s,l);let c=Ur(()=>this.run(),150);this.input.addEventListener("input",c),this.input.addEventListener("keydown",d=>{d.key==="Enter"?(d.preventDefault(),c.cancel(),this.input.value!==this.lastQuery?this.run():this.step(d.shiftKey?-1:1)):d.key==="Escape"&&(d.preventDefault(),d.stopPropagation(),this.input.value?(this.input.value="",this.run()):n.onClose())}),this.lastQuery=void 0}run(){let e=this.input.value;this.lastQuery=e;let{total:n,capped:a}=this.handlers.run(e);this.total=n,this.capped=a,this.index=-1,n>0?this.step(1):this.updateCount(),this.handlers.onResult?.(e,n,a)}step(e){this.total&&(this.index=((this.index+e)%this.total+this.total)%this.total,this.handlers.go(this.index),this.updateCount())}updateCount(){if(!this.input.value)this.count.textContent="";else if(!this.total)this.count.textContent=this.t("searchNone");else{let e=this.capped?"searchCountCapped":"searchCount";this.count.textContent=this.t(e,{current:this.index+1,total:this.total})}}focus(){this.input.focus(),this.input.select()}};function _n(t){return g("div",{class:"loader",part:"loading",attrs:{role:"status"}},bl(),g("span",{class:"loader-label",text:t("loading")}))}var bs="http://www.w3.org/2000/svg";function bl(){let t=document.createElementNS(bs,"svg");t.setAttribute("viewBox","0 0 120 120"),t.setAttribute("class","loader-mark"),t.setAttribute("aria-hidden","true"),t.setAttribute("focusable","false");let e=[["rect",{class:"loader-frame",x:"12",y:"16",width:"96",height:"88",rx:"18"}],["path",{class:"loader-frame",d:"M12 42 L108 42"}],["circle",{class:"loader-dot",cx:"29",cy:"29",r:"5"}],["path",{class:"loader-v",d:"M42 60 L60 86 L78 60",pathLength:"100"}]];for(let[n,a]of e){let r=document.createElementNS(bs,n);for(let[i,s]of Object.entries(a))r.setAttribute(i,s);t.append(r)}return t}function vs(t,e){return g("div",{class:"message",part:"error",attrs:{role:"alert"}},Ue("alert"),g("div",{},g("p",{class:"message-title",text:t}),e?g("p",{class:"message-detail",text:e}):null))}function Rt(t){return g("div",{class:"notice",part:"notice",attrs:{role:"note"}},Ue("alert"),g("span",{text:t}))}function xs(t){return g("div",{class:"empty",part:"empty",text:t("empty")})}var _s=new Map;function wn(t){let e=_s.get(t);return e||(e=new CSSStyleSheet,e.replaceSync(t),_s.set(t,e)),e}var yl=Object.freeze(["variant","theme","src","allow-remote","max-height","copy","search","download","header","dot","title","label","lang-ui","mode","edit-toggle","placeholder","syntax-theme","syntax-theme-dark","badge","history","fullscreen","status","json","json-src","json-path"]);function vl(t){return t instanceof HTMLTemplateElement?t.content.textContent??"":t.textContent??""}var Je=class extends HTMLElement{static type="base";static componentAttributes=[];static presets={simple:{},full:{}};static allowEmpty=!1;static keepCarriageReturns=!1;static dataAttributes=[];static fromData(e){return typeof e=="string"?e:Ft(e)}static upgradeProperties=["content"];static styles=[];static get observedAttributes(){return[...yl,...this.componentAttributes]}constructor(){super(),this.root=this.attachShadow({mode:"open"}),this.frame=g("div",{class:"vt",part:"container"}),this.syntaxTheme=null,this.updateSheets(null),this.live=g("div",{class:"sr-only",attrs:{"aria-live":"polite","aria-atomic":"true"}}),this.root.append(this.frame,this.live),this._content=void 0,this._data=void 0,this._fromJson=!1,this._dataAttributes=new Set,this.text=null,this.error=null,this.loading=!1,this.searchOpen=!1,this.searchQuery="",this.searchBar=null,this.t=ya("en"),this._loadToken=0,this._abort=null,this._renderQueued=!1,this._readyPending=!1,this._cleanups=[],this._observer=null,this._connected=!1,this.modeState=null,this.editHistory=null,this._historyCleanup=null,this._escapeFullscreen=null}get content(){return this.text??""}set content(e){let n=e==null?void 0:String(e);n!==void 0&&n===this._content&&n===this.text||(this._content=n,this._fromJson=!1,this._connected&&this.reload())}get data(){return this._data}set data(e){this._fromJson=!1,this.applyData(e)}applyData(e){this._data=e;let n=this.constructor,a;try{a=n.fromData(e)}catch(s){this._content="",this.setError(new ue("jsonUnusable",{},s));return}let{content:r,attributes:i={}}=typeof a=="string"?{content:a}:a;this.applyDataAttributes(i),this._content=r,this._connected&&this.setText(r)}applyDataAttributes(e){let n=this.constructor.dataAttributes,a=this._dataAttributes;this._dataAttributes=new Set;for(let[r,i]of Object.entries(e)){if(!n.includes(r)||i===null||i===void 0||this.hasAttribute(r)&&!a.has(r))continue;let s=i===!0?"":i===!1?"false":String(i).slice(0,2e3);this.getAttribute(r)!==s&&this.setAttribute(r,s),this._dataAttributes.add(r)}for(let r of a)this._dataAttributes.has(r)||this.removeAttribute(r)}loadJson(){let e=this.getAttribute("json-src")?.trim(),n=this.getAttribute("json"),a=this.querySelector(":scope > script[data-json], :scope > template[data-json]");if(!e&&n===null&&!a)return this._fromJson&&(this._fromJson=!1,this._content=void 0),!1;let r=++this._loadToken;if(this._abort?.abort(),this._abort=null,!e)return this.useJson(n??vl(a)),!0;let i=J();this.loading=!0,this.error=null,this.requestRender();let s=new AbortController;return this._abort=s,fa(e,{allowRemote:Ie(this.getAttribute("allow-remote"))===!0,maxSize:i.maxSize,timeout:i.fetchTimeout,signal:s.signal}).then(l=>r===this._loadToken&&this.useJson(l),l=>r===this._loadToken&&!ma(l)&&this.setError(l)),!0}useJson(e){this.loading=!1;let n;try{jt(e,J().maxSize),n=JSON.parse(e)}catch(r){this.setError(r instanceof ue?r:new ue("jsonInvalid",{message:r instanceof Error?r.message:""},r));return}let a=this.getAttribute("json-path")?.trim();if(a){let r=qr(n,a);if(!r.ok){this.setError(new ue("jsonPathMissing",{path:a.slice(0,100)}));return}n=r.value}this._fromJson=!0,this.applyData(n)}upgradeProperty(e){if(Object.prototype.hasOwnProperty.call(this,e)){let n=this[e];delete this[e],this[e]=n}}connectedCallback(){for(let n of new Set([...this.constructor.upgradeProperties,"data"]))this.upgradeProperty(n);this._cleanups.push(Br(n=>n.has("maxSize")?this.reload():this.requestRender()),rs(()=>this.applyTheme()),Jr(()=>this.requestRender())),this._observer=new MutationObserver(()=>{(this._content===void 0||this._fromJson)&&!this.hasAttribute("src")&&this.reload()}),this._observer.observe(this,{childList:!0,characterData:!0,subtree:!0});let e=()=>{document.fullscreenElement===this?this.setFullscreen("native"):this.frame.dataset.fullscreen==="native"&&this.setFullscreen(null)};document.addEventListener("fullscreenchange",e),this._cleanups.push(()=>document.removeEventListener("fullscreenchange",e)),this._connected=!0,this.reload()}disconnectedCallback(){this._connected=!1;for(let e of this._cleanups.splice(0))e();this._observer?.disconnect(),this._observer=null,this._abort?.abort(),this._abort=null}attributeChangedCallback(e,n,a){n===a||!this.isConnected||(e==="mode"&&(this.modeState=null),["src","allow-remote","json","json-src","json-path"].includes(e)?this.reload():e==="theme"?this.applyTheme():this.requestRender())}reload(){if((this._content===void 0||this._fromJson)&&this.loadJson())return;let e=++this._loadToken;this._abort?.abort(),this._abort=null;let n=J(),a=this.getAttribute("src");if(this._content!==void 0)this.setText(this._content);else if(a!==null&&a.trim()!==""){this.loading=!0,this.error=null,this.requestRender();let r=new AbortController;this._abort=r,fa(a,{allowRemote:Ie(this.getAttribute("allow-remote"))===!0,maxSize:n.maxSize,timeout:n.fetchTimeout,signal:r.signal}).then(i=>e===this._loadToken&&this.setText(i),i=>e===this._loadToken&&!ma(i)&&this.setError(i))}else this.setText(this.readInline()??"")}setText(e){this.loading=!1,this.editHistory=null;try{jt(e,J().maxSize)}catch(a){this.setError(a);return}let n=this.constructor;this.text=e.replace(n.keepCarriageReturns?/\r\n/g:/\r\n?/g,`
`),this.error=null,this.contentChanged(),this._readyPending=!0,this.requestRender()}setError(e){this.loading=!1,this._readyPending=!1,this.error=e,this.text=null,this.contentChanged(),this.requestRender();let{title:n,detail:a}=this.describeError(e);oe(this,ie.ERROR,{message:a||n,cause:e})}describeError(e){let n=this.t;if(e instanceof ue){let a={...e.params};for(let r of["size","limit"])typeof a[r]=="number"&&(a[r]=yn(Number(a[r]),this.locale));return{title:n("errorTitle"),detail:n(e.code,a)}}return{title:n("errorTitle"),detail:e instanceof Error?e.message:String(e)}}get editing(){return(this.modeState??ca(this.getAttribute("mode"),["view","edit"],"view"))==="edit"}edited(e){this.text=e,this._content=e,this.contentEdited(e),oe(this,ie.INPUT,{value:e})}contentEdited(e){}historyButtons(e){if(this.editHistory=e.history,Ie(this.getAttribute("history"))===!1)return[];let n=de({icon:"undo",label:this.t("undo"),key:"undo",part:"undo-button",onClick:()=>e.undo()}),a=de({icon:"redo",label:this.t("redo"),key:"redo",part:"redo-button",onClick:()=>e.redo()}),r=()=>{n.disabled=!e.history.canUndo,a.disabled=!e.history.canRedo};return r(),this._historyCleanup?.(),this._historyCleanup=e.history.subscribe(r),[n,a]}fullscreenButton(){if(!this.feature("fullscreen"))return null;let e=!!this.frame.dataset.fullscreen;return de({icon:e?"minimize":"maximize",label:this.t(e?"exitFullscreen":"fullscreen"),key:"fullscreen",part:"fullscreen-button",pressed:e,onClick:()=>this.toggleFullscreen()})}async toggleFullscreen(){let e=this.frame.dataset.fullscreen;if(e==="native"){await document.exitFullscreen?.().catch(()=>{});return}if(e==="window"){this.setFullscreen(null);return}if(document.fullscreenEnabled&&this.requestFullscreen)try{await this.requestFullscreen({navigationUI:"hide"});return}catch{}this.setFullscreen("window")}setFullscreen(e){e?this.frame.dataset.fullscreen=e:delete this.frame.dataset.fullscreen,e==="window"?(this._escapeFullscreen=n=>{n.key==="Escape"&&!n.defaultPrevented&&this.setFullscreen(null)},this.frame.addEventListener("keydown",this._escapeFullscreen)):this._escapeFullscreen&&(this.frame.removeEventListener("keydown",this._escapeFullscreen),this._escapeFullscreen=null),this.render(),this.root.querySelector('[data-focus-key="fullscreen"]')?.focus(),oe(this,ie.FULLSCREEN_CHANGE,{fullscreen:!!e})}editToggleButton(){return this.feature("edit-toggle")?de({icon:this.editing?"eye":"pencil",label:this.t(this.editing?"stopEditing":"edit"),key:"edit-toggle",part:"edit-button",pressed:this.editing,onClick:()=>{this.modeState=this.editing?"view":"edit",this.render(),oe(this,ie.MODE_CHANGE,{mode:this.modeState}),this.modeState==="edit"&&this.root.querySelector(".editor-input")?.focus()}}):null}readInline(){return $r(this)}contentChanged(){}get variant(){return ca(this.getAttribute("variant"),["simple","full"],"simple")}feature(e){let n=Ie(this.getAttribute(e));return n!==null?n:this.constructor.presets[this.variant][e]??!1}get locale(){let e=this.getAttribute("lang-ui")?.trim();return e&&/^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(e)?e:J().lang}get heading(){return Rr(this.getAttribute("label")??this.getAttribute("title"))}requestRender(){this._renderQueued||(this._renderQueued=!0,queueMicrotask(()=>{this._renderQueued=!1,this.isConnected&&this.render()}))}applyTheme(){let e=ss(this.getAttribute("theme"));this.frame.dataset.theme=e,this.applySyntaxTheme(as(e)?.colorScheme==="dark")}applySyntaxTheme(e){let n=J(),a=e&&this.getAttribute("syntax-theme-dark")||this.getAttribute("syntax-theme")||e&&n.syntaxThemeDark||n.syntaxTheme,r=ds(a);if(this.syntaxTheme=r,!r){this.updateSheets(null);return}let i=ps(r);if(i){this.updateSheets(i);return}hs(r).then(s=>{s&&this.syntaxTheme===r&&this.updateSheets(s)})}updateSheets(e){let a=this.constructor.styles.map(wn),r=[wn(Or),lt,wn(Ir),...a];this.frame.toggleAttribute("data-syntax-theme",!!e),this.root.adoptedStyleSheets=e?[...r.filter(i=>i!==wn(Nt)),e]:r}render(){let e=this.activeFocusKey(),n=this.root.activeElement,a=n instanceof HTMLTextAreaElement||n instanceof HTMLInputElement?[n.selectionStart,n.selectionEnd]:null;this.t=ya(this.locale),this.applyTheme();let r=Lr(this.getAttribute("max-height"));if(r?this.frame.style.setProperty("--_max-height",r):this.frame.style.removeProperty("--_max-height"),this.searchBar=null,this.frame.replaceChildren(),this.loading){this.frame.append(...this.chrome(null),g("div",{class:"body",part:"body"},_n(this.t))),this.frame.setAttribute("aria-busy","true");return}if(this.frame.removeAttribute("aria-busy"),this.error){let{title:s,detail:l}=this.describeError(this.error);this.frame.append(...this.chrome(null),vs(s,l));return}if(!this.text&&!this.editing&&!this.constructor.allowEmpty)this.frame.append(...this.chrome(null),xs(this.t));else{this.renderContent(this.frame);let s=this.searchBar;this.searchOpen&&this.searchQuery&&s?.run()}this.restoreFocus(e);let i=this.root.activeElement;if(a&&(i instanceof HTMLTextAreaElement||i instanceof HTMLInputElement)&&a[0]!==null)try{i.setSelectionRange(a[0],a[1])}catch{}this._readyPending&&(this._readyPending=!1,oe(this,ie.READY,{type:this.constructor.type}))}renderContent(e){throw new Error("renderContent() must be implemented.")}chrome(e){let n=(e?.actions??[]).filter(s=>s!==null),a=n.length?g("div",{class:"toolbar",part:"toolbar",attrs:{role:"toolbar","aria-label":this.t("actions")}},...n):null;if(!this.feature("header"))return a?.classList.add("floating"),[a,e?.tabs??null,this.searchBar?.element??null].filter(s=>s!==null);let r=this.heading,i=g("div",{class:"header",part:"header"},this.feature("dot")?g("span",{class:"dot",part:"status-dot",attrs:{"aria-hidden":"true"}}):null,r?g("span",{class:"title",part:"title",text:r,attrs:{title:r}}):null,e?.tabs??null,r?null:g("span",{class:"spacer"}),e?.badge&&Ie(this.getAttribute("badge"))!==!1?g("span",{class:"badge",part:"badge",text:e.badge}):null);return a&&i.append(a),this.searchBar?[i,this.searchBar.element]:[i]}copyButton(e,n=this.t("copy"),a="copy"){let r=de({icon:"copy",label:n,key:a,part:"copy-button",onClick:async()=>{let i=e(),s=await da(i,this.root);ys(r,"copy",s),this.announce(this.t(s?"copied":"copyFailed")),s&&oe(this,ie.COPY,{text:i})}});return r}copyTextButton(e,n,a){let r=g("button",{class:"text-btn",part:"copy-button",text:n,attrs:{type:"button","data-focus-key":a},on:{click:async()=>{let i=e(),s=await da(i,this.root);r.textContent=this.t(s?"copied":"copyFailed"),r.classList.toggle("done",s),setTimeout(()=>{r.textContent=n,r.classList.remove("done")},1500),this.announce(this.t(s?"copied":"copyFailed")),s&&oe(this,ie.COPY,{text:i})}}});return r}downloadName(e){let n=this.getAttribute("download"),a=n&&Ie(n)!==!1&&!/^(?:true|on|yes)$/i.test(n.trim())?n:null,r=/\.[a-z0-9]{1,10}$/i.test(this.heading)?this.heading:null;return Mr(a??r,e)}downloadButton(e,n,a){return de({icon:"download",label:this.t("download"),key:"download",part:"download-button",onClick:()=>Dr(e(),n,a)})}searchButton(e){return this.feature("search")?(this.searchOpen&&(this.searchBar=new xn(this.t,{run:n=>(this.searchQuery=n,e.run(n)),go:n=>e.go(n),onResult:(n,a,r)=>{n&&this.announce(a?this.t("searchResults",{total:r?`${a}+`:a}):this.t("searchNone")),oe(this,ie.SEARCH,{query:n,matches:a})},onClose:()=>{e.clear(),this.searchOpen=!1,this.searchQuery="",this.render(),this.root.querySelector('[data-focus-key="search"]')?.focus()}},this.searchQuery)),de({icon:"search",label:this.t("search"),key:"search",part:"search-button",pressed:this.searchOpen,onClick:()=>{this.searchOpen=!this.searchOpen,this.searchOpen||(this.searchQuery=""),this.render(),this.searchOpen&&this.searchBar?.focus()}})):null}announce(e){this.live.textContent="",setTimeout(()=>{this.live.textContent=e},50)}activeFocusKey(){let e=this.root.activeElement;return e instanceof HTMLElement?e.dataset.focusKey??null:null}restoreFocus(e){if(!e)return;let n=this.root.querySelector(`[data-focus-key="${CSS.escape(e)}"]`);n instanceof HTMLElement&&n.focus({preventScroll:!0})}};var $s=Oo(Fs(),1);var je=$s.default;function Hs(t){let e=t.regex,n={},a={begin:/\$\{/,end:/\}/,contains:["self",{begin:/:-/,contains:[n]}]};Object.assign(n,{className:"variable",variants:[{begin:e.concat(/\$[\w\d#@][\w\d_]*/,"(?![\\w\\d])(?![$])")},a]});let r={className:"subst",begin:/\$\(/,end:/\)/,contains:[t.BACKSLASH_ESCAPE]},i=t.inherit(t.COMMENT(),{match:[/(^|\s)/,/#.*$/],scope:{2:"comment"}}),s={begin:/<<-?\s*(?=\w+)/,starts:{contains:[t.END_SAME_AS_BEGIN({begin:/(\w+)/,end:/(\w+)/,className:"string"})]}},l={className:"string",begin:/"/,end:/"/,contains:[t.BACKSLASH_ESCAPE,n,r]};r.contains.push(l);let c={match:/\\"/},d={className:"string",begin:/'/,end:/'/},p={match:/\\'/},x={begin:/\$?\(\(/,end:/\)\)/,contains:[{begin:/\d+#[0-9a-f]+/,className:"number"},t.NUMBER_MODE,n]},b=["fish","bash","zsh","sh","csh","ksh","tcsh","dash","scsh"],w=t.SHEBANG({binary:`(${b.join("|")})`,relevance:10}),h={className:"function",begin:/\w[\w\d_]*\s*\(\s*\)\s*\{/,returnBegin:!0,contains:[t.inherit(t.TITLE_MODE,{begin:/\w[\w\d_]*/})],relevance:0},y=["if","then","else","elif","fi","time","for","while","until","in","do","done","case","esac","coproc","function","select"],N=["true","false"],I={match:/(\/[a-z._-]+)+/},P=["break","cd","continue","eval","exec","exit","export","getopts","hash","pwd","readonly","return","shift","test","times","trap","umask","unset"],H=["alias","bind","builtin","caller","command","declare","echo","enable","help","let","local","logout","mapfile","printf","read","readarray","source","sudo","type","typeset","ulimit","unalias"],B=["autoload","bg","bindkey","bye","cap","chdir","clone","comparguments","compcall","compctl","compdescribe","compfiles","compgroups","compquote","comptags","comptry","compvalues","dirs","disable","disown","echotc","echoti","emulate","fc","fg","float","functions","getcap","getln","history","integer","jobs","kill","limit","log","noglob","popd","print","pushd","pushln","rehash","sched","setcap","setopt","stat","suspend","ttyctl","unfunction","unhash","unlimit","unsetopt","vared","wait","whence","where","which","zcompile","zformat","zftp","zle","zmodload","zparseopts","zprof","zpty","zregexparse","zsocket","zstyle","ztcp"],q=["chcon","chgrp","chown","chmod","cp","dd","df","dir","dircolors","ln","ls","mkdir","mkfifo","mknod","mktemp","mv","realpath","rm","rmdir","shred","sync","touch","truncate","vdir","b2sum","base32","base64","cat","cksum","comm","csplit","cut","expand","fmt","fold","head","join","md5sum","nl","numfmt","od","paste","ptx","pr","sha1sum","sha224sum","sha256sum","sha384sum","sha512sum","shuf","sort","split","sum","tac","tail","tr","tsort","unexpand","uniq","wc","arch","basename","chroot","date","dirname","du","echo","env","expr","factor","groups","hostid","id","link","logname","nice","nohup","nproc","pathchk","pinky","printenv","printf","pwd","readlink","runcon","seq","sleep","stat","stdbuf","stty","tee","test","timeout","tty","uname","unlink","uptime","users","who","whoami","yes"];return{name:"Bash",aliases:["sh","zsh"],keywords:{$pattern:/\b[a-z][a-z0-9._-]+\b/,keyword:y,literal:N,built_in:[...P,...H,"set","shopt",...B,...q]},contains:[w,t.SHEBANG(),h,x,i,s,I,l,c,d,p,n]}}function Gs(t){let e=t.regex;return{name:"Diff",aliases:["patch"],contains:[{className:"meta",relevance:10,match:e.either(/^@@ +-\d+,\d+ +\+\d+,\d+ +@@/,/^@@ +-\d+ +\+\d+,\d+ +@@/,/^@@ +-\d+,\d+ +\+\d+ +@@/,/^@@ +-\d+ +\+\d+ +@@/,/^\*\*\* +\d+,\d+ +\*\*\*\*$/,/^--- +\d+,\d+ +----$/)},{className:"comment",variants:[{begin:e.either(/Index: /,/^index/,/={3,}/,/^-{3}/,/^\*{3} /,/^\+{3}/,/^diff --git/),end:/$/},{match:/^\*{15}$/}]},{className:"addition",begin:/^\+/,end:/$/},{className:"deletion",begin:/^-/,end:/$/},{className:"addition",begin:/^!/,end:/$/}]}}var Vs="[A-Za-z$_][0-9A-Za-z$_]*",cc=["as","in","of","if","for","while","finally","var","new","function","do","return","void","else","break","catch","instanceof","with","throw","case","default","try","switch","continue","typeof","delete","let","yield","const","class","debugger","async","await","static","import","from","export","extends","using"],uc=["true","false","null","undefined","NaN","Infinity"],qs=["Object","Function","Boolean","Symbol","Math","Date","Number","BigInt","String","RegExp","Array","Float32Array","Float64Array","Int8Array","Uint8Array","Uint8ClampedArray","Int16Array","Int32Array","Uint16Array","Uint32Array","BigInt64Array","BigUint64Array","Set","Map","WeakSet","WeakMap","ArrayBuffer","SharedArrayBuffer","Atomics","DataView","JSON","Promise","Generator","GeneratorFunction","AsyncFunction","Reflect","Proxy","Intl","WebAssembly"],Ks=["Error","EvalError","InternalError","RangeError","ReferenceError","SyntaxError","TypeError","URIError"],Ws=["setInterval","setTimeout","clearInterval","clearTimeout","require","exports","eval","isFinite","isNaN","parseFloat","parseInt","decodeURI","decodeURIComponent","encodeURI","encodeURIComponent","escape","unescape"],dc=["arguments","this","super","console","window","document","localStorage","sessionStorage","module","self","global"],pc=[].concat(Ws,qs,Ks);function Ys(t){let e=t.regex,n=(R,{after:j})=>{let E="</"+R[0].slice(1);return R.input.indexOf(E,j)!==-1},a=Vs,r={begin:"<>",end:"</>"},i=/<[A-Za-z0-9\\._:-]+\s*\/>/,s={begin:/<[A-Za-z0-9\\._:-]+/,end:/\/[A-Za-z0-9\\._:-]+>|\/>/,isTrulyOpeningTag:(R,j)=>{let E=R[0].length+R.index,L=R.input[E];if(L==="<"||L===","){j.ignoreMatch();return}L===">"&&(n(R,{after:E})||j.ignoreMatch());let D,W=R.input.substring(E);if(D=W.match(/^\s*=/)){j.ignoreMatch();return}if((D=W.match(/^\s+extends\s+/))&&D.index===0){j.ignoreMatch();return}}},l={$pattern:Vs,keyword:cc,literal:uc,built_in:pc,"variable.language":dc},c="[0-9](_?[0-9])*",d=`\\.(${c})`,p="0|[1-9](_?[0-9])*|0[0-7]*[89][0-9]*",x={className:"number",variants:[{begin:`(\\b(${p})((${d})|\\.)?|(${d}))[eE][+-]?(${c})\\b`},{begin:`\\b(${p})\\b((${d})\\b|\\.)?|(${d})\\b`},{begin:"\\b(0|[1-9](_?[0-9])*)n\\b"},{begin:"\\b0[xX][0-9a-fA-F](_?[0-9a-fA-F])*n?\\b"},{begin:"\\b0[bB][0-1](_?[0-1])*n?\\b"},{begin:"\\b0[oO][0-7](_?[0-7])*n?\\b"},{begin:"\\b0[0-7]+n?\\b"}],relevance:0},b={className:"subst",begin:"\\$\\{",end:"\\}",keywords:l,contains:[]},w={begin:".?html`",end:"",starts:{end:"`",returnEnd:!1,contains:[t.BACKSLASH_ESCAPE,b],subLanguage:"xml"}},h={begin:".?css`",end:"",starts:{end:"`",returnEnd:!1,contains:[t.BACKSLASH_ESCAPE,b],subLanguage:"css"}},y={begin:".?gql`",end:"",starts:{end:"`",returnEnd:!1,contains:[t.BACKSLASH_ESCAPE,b],subLanguage:"graphql"}},N={className:"string",begin:"`",end:"`",contains:[t.BACKSLASH_ESCAPE,b]},P={className:"comment",variants:[t.COMMENT(/\/\*\*(?!\/)/,"\\*/",{relevance:0,contains:[{begin:"(?=@[A-Za-z]+)",relevance:0,contains:[{className:"doctag",begin:"@[A-Za-z]+"},{className:"type",begin:"\\{",end:"\\}",excludeEnd:!0,excludeBegin:!0,relevance:0},{className:"variable",begin:a+"(?=\\s*(-)|$)",endsParent:!0,relevance:0},{begin:/(?=[^\n])\s/,relevance:0}]}]}),t.C_BLOCK_COMMENT_MODE,t.C_LINE_COMMENT_MODE]},H=[t.APOS_STRING_MODE,t.QUOTE_STRING_MODE,w,h,y,N,{match:/\$\d+/},x];b.contains=H.concat({begin:/\{/,end:/\}/,keywords:l,contains:["self"].concat(H)});let B=[].concat(P,b.contains),q=B.concat([{begin:/(\s*)\(/,end:/\)/,keywords:l,contains:["self"].concat(B)}]),X={className:"params",begin:/(\s*)\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:l,contains:q},ne={variants:[{match:[/class/,/\s+/,a,/\s+/,/extends/,/\s+/,e.concat(a,"(",e.concat(/\./,a),")*")],scope:{1:"keyword",3:"title.class",5:"keyword",7:"title.class.inherited"}},{match:[/class/,/\s+/,a],scope:{1:"keyword",3:"title.class"}}]},re={relevance:0,match:e.either(/\bJSON/,/\b[A-Z][a-z]+([A-Z][a-z]*|\d)*/,/\b[A-Z]{2,}([A-Z][a-z]+|\d)+([A-Z][a-z]*)*/,/\b[A-Z]{2,}[a-z]+([A-Z][a-z]+|\d)*([A-Z][a-z]*)*/),className:"title.class",keywords:{_:[...qs,...Ks]}},Re={label:"use_strict",className:"meta",relevance:10,begin:/^\s*['"]use (strict|asm)['"]/},Se={variants:[{match:[/function/,/\s+/,a,/(?=\s*\()/]},{match:[/function/,/\s*(?=\()/]}],className:{1:"keyword",3:"title.function"},label:"func.def",contains:[X],illegal:/%/},ae={relevance:0,match:/\b[A-Z][A-Z_0-9]+\b/,className:"variable.constant"};function ye(R){return e.concat("(?!",R.join("|"),")")}let Pe={match:e.concat(/\b/,ye([...Ws,"super","import","await"].map(R=>`${R}\\s*\\(`)),a,e.lookahead(/\s*\(/)),className:"title.function",relevance:0},ke={begin:e.concat(/\./,e.lookahead(e.concat(a,/(?![0-9A-Za-z$_(])/))),end:a,excludeBegin:!0,keywords:"prototype",className:"property",relevance:0},Me={match:[/get|set/,/\s+/,a,/(?=\()/],className:{1:"keyword",3:"title.function"},contains:[{begin:/\(\)/},X]},_="(\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)|"+t.UNDERSCORE_IDENT_RE+")\\s*=>",S={match:[/const|var|let/,/\s+/,a,/\s*/,/=\s*/,/(async\s*)?/,e.lookahead(_)],keywords:"async",className:{1:"keyword",3:"title.function"},contains:[X]};return{name:"JavaScript",aliases:["js","jsx","mjs","cjs"],keywords:l,exports:{PARAMS_CONTAINS:q,CLASS_REFERENCE:re},illegal:/#(?![$_A-Za-z])/,contains:[t.SHEBANG({label:"shebang",binary:"node",relevance:5}),Re,t.APOS_STRING_MODE,t.QUOTE_STRING_MODE,w,h,y,N,P,{match:/\$\d+/},x,re,{scope:"attr",match:a+e.lookahead(":"),relevance:0},S,{begin:"("+t.RE_STARTERS_RE+"|\\b(case|return|throw)\\b)\\s*",keywords:"return throw case",relevance:0,contains:[P,t.REGEXP_MODE,{className:"function",begin:_,returnBegin:!0,end:"\\s*=>",contains:[{className:"params",variants:[{begin:t.UNDERSCORE_IDENT_RE,relevance:0},{className:null,begin:/\(\s*\)/,skip:!0},{begin:/(\s*)\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:l,contains:q}]}]},{begin:/,/,relevance:0},{match:/\s+/,relevance:0},{variants:[{begin:r.begin,end:r.end},{match:i},{begin:s.begin,"on:begin":s.isTrulyOpeningTag,end:s.end}],subLanguage:"xml",contains:[{begin:s.begin,end:s.end,skip:!0,contains:["self"]}]}]},Se,{beginKeywords:"while if switch catch for"},{begin:"\\b(?!function)"+t.UNDERSCORE_IDENT_RE+"\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)\\s*\\{",returnBegin:!0,label:"func.def",contains:[X,t.inherit(t.TITLE_MODE,{begin:a,className:"title.function"})]},{match:/\.\.\./,relevance:0},ke,{match:"\\$"+a,relevance:0},{match:[/\bconstructor(?=\s*\()/],className:{1:"title.function"},contains:[X]},Pe,ae,ne,Me,{match:/\$[(.]/}]}}var hc="([-+]?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)|NaN|[-+]?Infinity",fc={scope:"number",match:hc,relevance:0};function Zs(t){let e={className:"attr",begin:/(("(\\.|[^\\"\r\n])*")|('(\\.|[^\\'\r\n])*'))(?=\s*:)/,relevance:1.01},n={match:/[{}[\],:]/,className:"punctuation",relevance:0},a=["true","false","null"],r={scope:"literal",beginKeywords:a.join(" ")};return{name:"JSON",aliases:["jsonc","json5"],keywords:{literal:a},contains:[e,n,t.APOS_STRING_MODE,t.QUOTE_STRING_MODE,r,fc,t.C_LINE_COMMENT_MODE,t.C_BLOCK_COMMENT_MODE],illegal:"\\S"}}function Js(t){let e=t.regex,n={begin:/<\/?[A-Za-z_]/,end:">",subLanguage:"xml",relevance:0},a={match:/^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/},r={className:"code",variants:[{begin:"(`{3,})[^`](.|\\n)*?\\1`*[ ]*"},{begin:"(~{3,})[^~](.|\\n)*?\\1~*[ ]*"},{begin:"```",end:"```+[ ]*$"},{begin:"~~~",end:"~~~+[ ]*$"},{begin:"`.+?`"},{begin:"(?=^( {4}|\\t))",contains:[{begin:"^( {4}|\\t)",end:"(\\n)$"}],relevance:0}]},i={className:"bullet",begin:"^[ 	]*([*+-]|(\\d+\\.))(?=\\s+)",end:"\\s+",excludeEnd:!0},s={begin:/^\[[^\n]+\]:/,returnBegin:!0,contains:[{className:"symbol",begin:/\[/,end:/\]/,excludeBegin:!0,excludeEnd:!0},{className:"link",begin:/:\s*/,end:/$/,excludeBegin:!0}]},l=/[A-Za-z][A-Za-z0-9+.-]*/,c={variants:[{begin:/\[.+?\]\[.*?\]/,relevance:0},{begin:/\[.+?\]\(((data|javascript|mailto):|(?:http|ftp)s?:\/\/).*?\)/,relevance:2},{begin:e.concat(/\[.+?\]\(/,l,/:\/\/.*?\)/),relevance:2},{begin:/\[.+?\]\([./?&#].*?\)/,relevance:1},{begin:/\[.*?\]\(.*?\)/,relevance:0}],returnBegin:!0,contains:[{match:/\[(?=\])/},{className:"string",relevance:0,begin:"\\[",end:"\\]",excludeBegin:!0,returnEnd:!0},{className:"link",relevance:0,begin:"\\]\\(",end:"\\)",excludeBegin:!0,excludeEnd:!0},{className:"symbol",relevance:0,begin:"\\]\\[",end:"\\]",excludeBegin:!0,excludeEnd:!0}]},d={className:"strong",contains:[],variants:[{begin:/_{2}(?!\s)/,end:/_{2}/},{begin:/\*{2}(?!\s)/,end:/\*{2}/}]},p={className:"emphasis",contains:[],variants:[{begin:/\*(?![*\s])/,end:/\*/},{begin:/_(?![_\s])/,end:/_/,relevance:0}]},x=t.inherit(d,{contains:[]}),b=t.inherit(p,{contains:[]});d.contains.push(b),p.contains.push(x);let w=[n,c];return[d,p,x,b].forEach(I=>{I.contains=I.contains.concat(w)}),w=w.concat(d,p),{name:"Markdown",aliases:["md","mkdown","mkd"],contains:[{className:"section",variants:[{begin:"^#{1,6}",end:"$",contains:w},{begin:"(?=^.+?\\n[=-]{2,}$)",contains:[{begin:"^[=-]*$"},{begin:"^",end:"\\n",contains:w}]}]},n,i,a,d,p,{className:"quote",begin:"^>\\s+",contains:w,end:"$"},r,c,s,{scope:"literal",match:/&([a-zA-Z0-9]+|#[0-9]{1,7}|#[Xx][0-9a-fA-F]{1,6});/}]}}function Xs(t){return{name:"Plain text",aliases:["text","txt"],disableAutodetect:!0}}function Qs(t){let e=t.regex,n=/[\p{XID_Start}_]\p{XID_Continue}*/u,a=["and","as","assert","async","await","break","case","class","continue","def","del","elif","else","except","finally","for","from","global","if","import","in","is","lambda","lazy","match","nonlocal|10","not","or","pass","raise","return","try","while","with","yield"],l={$pattern:/[A-Za-z]\w+|__\w+__/,keyword:a,built_in:["__import__","abs","aiter","all","anext","any","ascii","bin","bool","breakpoint","bytearray","bytes","callable","chr","classmethod","compile","complex","delattr","dict","dir","divmod","enumerate","eval","exec","filter","float","format","frozendict","frozenset","getattr","globals","hasattr","hash","help","hex","id","input","int","isinstance","issubclass","iter","len","list","locals","map","max","memoryview","min","next","object","oct","open","ord","pow","print","property","range","repr","reversed","round","sentinel","set","setattr","slice","sorted","staticmethod","str","sum","super","tuple","type","vars","zip"],literal:["__debug__","Ellipsis","False","None","NotImplemented","True"],type:["Any","Callable","Coroutine","Dict","List","Literal","Generic","Optional","Sequence","Set","Tuple","Type","Union"]},c={className:"meta",begin:/^(>>>|\.\.\.) /},d={className:"subst",begin:/\{/,end:/\}/,keywords:l,illegal:/#/},p={begin:/\{\{/,relevance:0},x={className:"string",contains:[t.BACKSLASH_ESCAPE],variants:[{begin:/([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?'''/,end:/'''/,contains:[t.BACKSLASH_ESCAPE,c],relevance:10},{begin:/([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?"""/,end:/"""/,contains:[t.BACKSLASH_ESCAPE,c],relevance:10},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])'''/,end:/'''/,contains:[t.BACKSLASH_ESCAPE,c,p,d]},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])"""/,end:/"""/,contains:[t.BACKSLASH_ESCAPE,c,p,d]},{begin:/([uU]|[rR])'/,end:/'/,relevance:10},{begin:/([uU]|[rR])"/,end:/"/,relevance:10},{begin:/([bB]|[bB][rR]|[rR][bB])'/,end:/'/},{begin:/([bB]|[bB][rR]|[rR][bB])"/,end:/"/},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])'/,end:/'/,contains:[t.BACKSLASH_ESCAPE,p,d]},{begin:/([fFtT][rR]|[rR][fFtT]|[fFtT])"/,end:/"/,contains:[t.BACKSLASH_ESCAPE,p,d]},t.APOS_STRING_MODE,t.QUOTE_STRING_MODE]},b="[0-9](_?[0-9])*",w=`(\\b(${b}))?\\.(${b})|\\b(${b})\\.`,h=`\\b|${a.join("|")}`,y={className:"number",relevance:0,variants:[{begin:`(\\b(${b})|(${w}))[eE][+-]?(${b})[jJ]?(?=${h})`},{begin:`(${w})[jJ]?`},{begin:`\\b([1-9](_?[0-9])*|0+(_?0)*)[lLjJ]?(?=${h})`},{begin:`\\b0[bB](_?[01])+[lL]?(?=${h})`},{begin:`\\b0[oO](_?[0-7])+[lL]?(?=${h})`},{begin:`\\b0[xX](_?[0-9a-fA-F])+[lL]?(?=${h})`},{begin:`\\b(${b})[jJ](?=${h})`}]},N={className:"comment",begin:e.lookahead(/# type:/),end:/$/,keywords:l,contains:[{begin:/# type:/},{begin:/#/,end:/\b\B/,endsWithParent:!0}]},I={className:"params",variants:[{className:"",begin:/\(\s*\)/,skip:!0},{begin:/\(/,end:/\)/,excludeBegin:!0,excludeEnd:!0,keywords:l,contains:["self",c,y,x,t.HASH_COMMENT_MODE]}]};return d.contains=[x,y,c],{name:"Python",aliases:["py","gyp","ipython"],unicodeRegex:!0,keywords:l,illegal:/(<\/|\?)|=>/,contains:[c,y,{scope:"variable.language",match:/\bself\b/},{beginKeywords:"if",relevance:0},{match:/\bor\b/,scope:"keyword"},x,N,t.HASH_COMMENT_MODE,{match:[/\bdef/,/\s+/,n],scope:{1:"keyword",3:"title.function"},contains:[I]},{variants:[{match:[/\bclass/,/\s+/,n,/\s*/,/\(\s*/,n,/\s*\)/]},{match:[/\bclass/,/\s+/,n]}],scope:{1:"keyword",3:"title.class",6:"title.class.inherited"}},{className:"meta",begin:/^[\t ]*@/,end:/(?=#)|$/,contains:[y,I,x]}]}}function ei(t){return{name:"Shell Session",aliases:["console","shellsession"],contains:[{className:"meta.prompt",begin:/^\s{0,3}[./~\w\d[\]()@-]*[>%$#][ ]?/,starts:{end:/[^\\](?=\s*$)/,subLanguage:"bash"}}]}}function ti(t){let e=t.regex,n=e.concat(/[\p{L}_]/u,e.optional(/[\p{L}0-9_.-]*:/u),/[\p{L}0-9_.-]*/u),a=/[\p{L}0-9._:-]+/u,r={className:"symbol",begin:/&[a-z]+;|&#[0-9]+;|&#x[a-f0-9]+;/},i={begin:/\s/,contains:[{className:"keyword",begin:/#?[a-z_][a-z1-9_-]+/,illegal:/\n/}]},s=t.inherit(i,{begin:/\(/,end:/\)/}),l=t.inherit(t.APOS_STRING_MODE,{className:"string"}),c=t.inherit(t.QUOTE_STRING_MODE,{className:"string"}),d={endsWithParent:!0,illegal:/</,relevance:0,contains:[{className:"attr",begin:a,relevance:0},{begin:/=\s*/,relevance:0,contains:[{className:"string",endsParent:!0,variants:[{begin:/"/,end:/"/,contains:[r]},{begin:/'/,end:/'/,contains:[r]},{begin:/[^\s"'=<>`]+/}]}]}]};return{name:"HTML, XML",aliases:["html","xhtml","rss","atom","xjb","xsd","xsl","plist","wsf","svg"],case_insensitive:!0,unicodeRegex:!0,contains:[{className:"meta",begin:/<![a-z]/,end:/>/,relevance:10,contains:[i,c,l,s,{begin:/\[/,end:/\]/,contains:[{className:"meta",begin:/<![a-z]/,end:/>/,contains:[i,s,c,l]}]}]},t.COMMENT(/<!--/,/-->/,{relevance:10}),{begin:/<!\[CDATA\[/,end:/\]\]>/,relevance:10},r,{className:"meta",end:/\?>/,variants:[{begin:/<\?xml/,relevance:10,contains:[c]},{begin:/<\?[a-z][a-z0-9]+/}]},{className:"tag",begin:/<style(?=\s|>)/,end:/>/,keywords:{name:"style"},contains:[d],starts:{end:/<\/style>/,returnEnd:!0,subLanguage:"css"}},{className:"tag",begin:/<script(?=\s|>)/,end:/>/,keywords:{name:"script"},contains:[d],starts:{end:/<\/script>/,returnEnd:!0,subLanguage:"javascript"}},{className:"tag",begin:/<>|<\/>/},{className:"tag",begin:e.concat(/</,e.lookahead(e.concat(n,e.either(/\/>/,/>/,/\s/)))),end:/\/?>/,contains:[{className:"name",begin:n,relevance:0,starts:d}]},{className:"tag",begin:e.concat(/<\//,e.lookahead(e.concat(n,/>/))),contains:[{className:"name",begin:n,relevance:0},{begin:/>/,relevance:0,endsParent:!0}]}]}}function ni(t){let e="true false yes no null",n="[\\w#;/?:@&=+$,.~*'()[\\]]+",a={className:"attr",variants:[{begin:/[\w*@][\w*@ :()\./-]*:(?=[ \t]|$)/},{begin:/"[\w*@][\w*@ :()\./-]*":(?=[ \t]|$)/},{begin:/'[\w*@][\w*@ :()\./-]*':(?=[ \t]|$)/}]},r={className:"template-variable",variants:[{begin:/\{\{/,end:/\}\}/},{begin:/%\{/,end:/\}/}]},i={className:"string",relevance:0,begin:/'/,end:/'/,contains:[{match:/''/,scope:"char.escape",relevance:0}]},s={className:"string",relevance:0,variants:[{begin:/"/,end:/"/},{begin:/\S+/}],contains:[t.BACKSLASH_ESCAPE,r]},l=t.inherit(s,{variants:[{begin:/'/,end:/'/,contains:[{begin:/''/,relevance:0}]},{begin:/"/,end:/"/},{begin:/[^\s,{}[\]]+/}]}),b={className:"number",begin:"\\b"+"[0-9]{4}(-[0-9][0-9]){0,2}"+"([Tt \\t][0-9][0-9]?(:[0-9][0-9]){2})?"+"(\\.[0-9]*)?"+"([ \\t])*(Z|[-+][0-9][0-9]?(:[0-9][0-9])?)?"+"\\b"},w={end:",",endsWithParent:!0,excludeEnd:!0,keywords:e,relevance:0},h={begin:/\{/,end:/\}/,contains:[w],illegal:"\\n",relevance:0},y={begin:"\\[",end:"\\]",contains:[w],illegal:"\\n",relevance:0},N=[a,{className:"meta",begin:"^---\\s*$",relevance:10},{className:"string",begin:"[\\|>]([1-9]?[+-])?[ ]*\\n( +)[^ ][^\\n]*\\n(\\2[^\\n]+\\n?)*"},{begin:"<%[%=-]?",end:"[%-]?%>",subLanguage:"ruby",excludeBegin:!0,excludeEnd:!0,relevance:0},{className:"type",begin:"!\\w+!"+n},{className:"type",begin:"!<"+n+">"},{className:"type",begin:"!"+n},{className:"type",begin:"!!"+n},{className:"meta",begin:"&"+t.UNDERSCORE_IDENT_RE+"$"},{className:"meta",begin:"\\*"+t.UNDERSCORE_IDENT_RE+"$"},{className:"bullet",begin:"-(?=[ ]|$)",relevance:0},t.HASH_COMMENT_MODE,{beginKeywords:e,keywords:{literal:e}},b,{className:"number",begin:t.C_NUMBER_RE+"\\b",relevance:0},h,y,i,s],I=[...N];return I.pop(),I.push(l),w.contains=I,{name:"YAML",case_insensitive:!0,aliases:["yml"],contains:N}}var Nn=Object.freeze({"1c":"",abnf:"",accesslog:"",actionscript:"as",ada:"",angelscript:"asc",apache:"apacheconf",applescript:"osascript",arcade:"",arduino:"ino",armasm:"arm",asciidoc:"adoc",aspectj:"",autohotkey:"ahk",autoit:"",avrasm:"",awk:"",axapta:"x++",bash:"sh zsh",basic:"",bnf:"",brainfuck:"bf",c:"h",cal:"",capnproto:"capnp",ceylon:"",clean:"dcl icl",clojure:"clj edn","clojure-repl":"",cmake:"cmake.in",coffeescript:"coffee cson iced",coq:"",cos:"cls",cpp:"c++ cc cxx h++ hh hpp hxx",crmsh:"crm pcmk",crystal:"cr",csharp:"c# cs",csp:"",css:"",d:"",dart:"",delphi:"dfm dpr pas pascal",diff:"patch",django:"jinja",dns:"bind zone",dockerfile:"docker",dos:"bat batch cmd",dsconfig:"",dts:"",dust:"dst",ebnf:"",elixir:"ex exs",elm:"",erb:"",erlang:"erl","erlang-repl":"",excel:"xls xlsx",fix:"",flix:"",fortran:"f90 f95",freedesktop:"desktop systemd",fsharp:"f# fs",gams:"gms",gauss:"gss",gcode:"nc",gherkin:"feature",glsl:"",gml:"",go:"golang",golo:"",gradle:"",graphql:"gql",groovy:"",haml:"",handlebars:"hbs html.handlebars html.hbs htmlbars",haskell:"hs",haxe:"hx",hsp:"",http:"https",hy:"hylang",inform7:"i7",ini:"toml",irpf90:"",isbl:"",java:"jsp",javascript:"cjs js jsx mjs","jboss-cli":"wildfly-cli",json:"json5 jsonc",julia:"","julia-repl":"jldoctest",kotlin:"kt ktm kts ktx",lasso:"lassoscript ls",latex:"tex",ldif:"",leaf:"",less:"",lisp:"",livecodeserver:"",livescript:"ls",llvm:"",lsl:"",lua:"pluto",makefile:"mak make mk",markdown:"md mkd mkdown",mathematica:"mma wl",matlab:"",maxima:"",mel:"",mercury:"m moo",mipsasm:"mips",mizar:"",mojolicious:"",monkey:"",moonscript:"moon",n1ql:"",nestedtext:"nt",nginx:"nginxconf",nim:"",nix:"nixos","node-repl":"",nsis:"",objectivec:"mm obj-c obj-c++ objc objective-c++",ocaml:"ml",openscad:"scad",oxygene:"",parser3:"",perl:"pl pm",pf:"pf.conf",pgsql:"postgres postgresql",php:"","php-template":"",plaintext:"text txt",pony:"",powershell:"ps ps1 pwsh",processing:"pde",profile:"",prolog:"",properties:"",protobuf:"proto",puppet:"pp",purebasic:"pb pbi",python:"gyp ipython py","python-repl":"pycon",q:"k kdb",qml:"qt",r:"",reasonml:"re",rib:"",roboconf:"graph instances",routeros:"mikrotik",rsl:"",ruby:"gemspec irb podspec rb thor",ruleslanguage:"",rust:"rs",sas:"",scala:"",scheme:"scm",scilab:"sci",scss:"",shell:"console shellsession",smali:"",smalltalk:"st",sml:"ml",sqf:"",sql:"",stan:"stanfuncs",stata:"ado do",step21:"p21 step stp",stylus:"styl",subunit:"",swift:"",taggerscript:"",tap:"",tcl:"tk",thrift:"",tp:"",twig:"craftcms",typescript:"cts mts ts tsx",vala:"",vbnet:"vb",vbscript:"vbs","vbscript-html":"",verilog:"sv svh v",vhdl:"",vim:"",wasm:"",wren:"",x86asm:"",xl:"tao",xml:"atom html plist rss svg wsf xhtml xjb xsd xsl",xquery:"xpath xq xqm",yaml:"yml",zephir:"zep"});function mc(t,e){this.v=t,this.k=e}function ai(t,e){(e==null||e>t.length)&&(e=t.length);for(var n=0,a=Array(e);n<e;n++)a[n]=t[n];return a}function gc(t){if(Array.isArray(t))return t}function bc(t,e){var n=t==null?null:typeof Symbol<"u"&&t[Symbol.iterator]||t["@@iterator"];if(n!=null){var a,r,i,s,l=[],c=!0,d=!1;try{if(i=(n=n.call(t)).next,e===0){if(Object(n)!==n)return;c=!1}else for(;!(c=(a=i.call(n)).done)&&(l.push(a.value),l.length!==e);c=!0);}catch(p){d=!0,r=p}finally{try{if(!c&&n.return!=null&&(s=n.return(),Object(s)!==s))return}finally{if(d)throw r}}return l}}function yc(){throw new TypeError(`Invalid attempt to destructure non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`)}function vc(t,e){return gc(t)||bc(t,e)||xc(t,e)||yc()}function xc(t,e){if(t){if(typeof t=="string")return ai(t,e);var n={}.toString.call(t).slice(8,-1);return n==="Object"&&t.constructor&&(n=t.constructor.name),n==="Map"||n==="Set"?Array.from(t):n==="Arguments"||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)?ai(t,e):void 0}}function Cn(t){var e,n;function a(i,s){try{var l=t[i](s),c=l.value,d=c instanceof mc;Promise.resolve(d?c.v:c).then(function(p){if(d){var x=i==="return"&&c.k?i:"next";if(!c.k||p.done)return a(x,p);p=t[x](p).value}r(!!l.done,p)},function(p){a("throw",p)})}catch(p){r(2,p)}}function r(i,s){i===2?e.reject(s):e.resolve({value:s,done:i}),(e=e.next)?a(e.key,e.arg):n=null}this._invoke=function(i,s){return new Promise(function(l,c){var d={key:i,arg:s,resolve:l,reject:c,next:null};n?n=n.next=d:(e=n=d,a(i,s))})},typeof t.return!="function"&&(this.return=void 0)}Cn.prototype[typeof Symbol=="function"&&Symbol.asyncIterator||"@@asyncIterator"]=function(){return this},Cn.prototype.next=function(t){return this._invoke("next",t)},Cn.prototype.throw=function(t){return this._invoke("throw",t)},Cn.prototype.return=function(t){return this._invoke("return",t)};var yi=Object.entries,ri=Object.setPrototypeOf,_c=Object.isFrozen,vi=Object.getPrototypeOf,xi=Object.getOwnPropertyDescriptor,pe=Object.freeze,fe=Object.seal,It=Object.create,_i=typeof Reflect<"u"&&Reflect,ja=_i.apply,Fa=_i.construct;pe||(pe=function(e){return e});fe||(fe=function(e){return e});ja||(ja=function(e,n){for(var a=arguments.length,r=new Array(a>2?a-2:0),i=2;i<a;i++)r[i-2]=arguments[i];return e.apply(n,r)});Fa||(Fa=function(e){for(var n=arguments.length,a=new Array(n>1?n-1:0),r=1;r<n;r++)a[r-1]=arguments[r];return new e(...a)});var He=te(Array.prototype.forEach);Array.prototype.indexOf;var wc=te(Array.prototype.lastIndexOf),si=te(Array.prototype.pop),Wt=te(Array.prototype.push),Ec=te(Array.prototype.slice),Ac=te(Array.prototype.splice),Dt=Array.isArray,Ra=wi(Set),Ma=te(Set.prototype.add),Yt=te(Set.prototype.has),pt=te(String.prototype.toLowerCase),Oa=te(String.prototype.toString),ii=te(String.prototype.match),Zt=te(String.prototype.replace),oi=te(String.prototype.indexOf),Tc=te(String.prototype.trim),Sc=te(Number.prototype.toString),kc=te(Boolean.prototype.toString),li=typeof BigInt>"u"?null:te(BigInt.prototype.toString),ci=typeof Symbol>"u"?null:te(Symbol.prototype.toString),_e=te(Object.prototype.hasOwnProperty),Jt=te(Object.prototype.toString),he=te(RegExp.prototype.test),Ge=wi(TypeError);function te(t){return function(e){e instanceof RegExp&&(e.lastIndex=0);for(var n=arguments.length,a=new Array(n>1?n-1:0),r=1;r<n;r++)a[r-1]=arguments[r];return ja(t,e,a)}}function wi(t){return function(){for(var e=arguments.length,n=new Array(e),a=0;a<e;a++)n[a]=arguments[a];return Fa(t,n)}}function G(t,e){let n=arguments.length>2&&arguments[2]!==void 0?arguments[2]:pt;if(ri&&ri(t,null),!Dt(e))return t;let a=e.length;for(;a--;){let r=e[a];if(typeof r=="string"){let i=n(r);i!==r&&(_c(e)||(e[a]=i),r=i)}t[r]=!0}return t}function Nc(t){for(let e=0;e<t.length;e++)_e(t,e)||(t[e]=null);return t}function Te(t){let e=It(null);for(let a of yi(t)){var n=vc(a,2);let r=n[0],i=n[1];_e(t,r)&&(Dt(i)?e[r]=Nc(i):i&&typeof i=="object"&&i.constructor===Object?e[r]=Te(i):e[r]=i)}return e}function Cc(t){switch(typeof t){case"string":return t;case"number":return Sc(t);case"boolean":return kc(t);case"bigint":return li?li(t):"0";case"symbol":return ci?ci(t):"Symbol()";case"undefined":return Jt(t);case"function":case"object":{if(t===null)return Jt(t);let e=t,n=Ce(e,"toString");if(typeof n=="function"){let a=n(e);return typeof a=="string"?a:Jt(a)}return Jt(t)}default:return Jt(t)}}function Ce(t,e){for(;t!==null;){let a=xi(t,e);if(a){if(a.get)return te(a.get);if(typeof a.value=="function")return te(a.value)}t=vi(t)}function n(){return null}return n}function Lc(t,e){for(;t!==null;){let n=xi(t,e);if(n)return n.get?te(n.get):null;t=vi(t)}return null}function Rc(t){try{return he(t,""),!0}catch{return!1}}var ui=pe(["a","abbr","acronym","address","area","article","aside","audio","b","bdi","bdo","big","blink","blockquote","body","br","button","canvas","caption","center","cite","code","col","colgroup","content","data","datalist","dd","decorator","del","details","dfn","dialog","dir","div","dl","dt","element","em","fieldset","figcaption","figure","font","footer","form","h1","h2","h3","h4","h5","h6","head","header","hgroup","hr","html","i","img","input","ins","kbd","label","legend","li","main","map","mark","marquee","menu","menuitem","meter","nav","nobr","ol","optgroup","option","output","p","picture","pre","progress","q","rp","rt","ruby","s","samp","search","section","select","shadow","slot","small","source","spacer","span","strike","strong","style","sub","summary","sup","table","tbody","td","template","textarea","tfoot","th","thead","time","tr","track","tt","u","ul","var","video","wbr"]),Ia=pe(["svg","a","altglyph","altglyphdef","altglyphitem","animatecolor","animatemotion","animatetransform","circle","clippath","defs","desc","ellipse","enterkeyhint","exportparts","filter","font","g","glyph","glyphref","hkern","image","inputmode","line","lineargradient","marker","mask","metadata","mpath","part","path","pattern","polygon","polyline","radialgradient","rect","stop","style","switch","symbol","text","textpath","title","tref","tspan","view","vkern"]),Da=pe(["feBlend","feColorMatrix","feComponentTransfer","feComposite","feConvolveMatrix","feDiffuseLighting","feDisplacementMap","feDistantLight","feDropShadow","feFlood","feFuncA","feFuncB","feFuncG","feFuncR","feGaussianBlur","feImage","feMerge","feMergeNode","feMorphology","feOffset","fePointLight","feSpecularLighting","feSpotLight","feTile","feTurbulence"]),Mc=pe(["animate","color-profile","cursor","discard","font-face","font-face-format","font-face-name","font-face-src","font-face-uri","foreignobject","hatch","hatchpath","mesh","meshgradient","meshpatch","meshrow","missing-glyph","script","set","solidcolor","unknown","use"]),Pa=pe(["math","menclose","merror","mfenced","mfrac","mglyph","mi","mlabeledtr","mmultiscripts","mn","mo","mover","mpadded","mphantom","mroot","mrow","ms","mspace","msqrt","mstyle","msub","msup","msubsup","mtable","mtd","mtext","mtr","munder","munderover","mprescripts"]),Oc=pe(["maction","maligngroup","malignmark","mlongdiv","mscarries","mscarry","msgroup","mstack","msline","msrow","semantics","annotation","annotation-xml","mprescripts","none"]),di=pe(["#text"]),pi=pe(["accept","action","align","alt","autocapitalize","autocomplete","autopictureinpicture","autoplay","background","bgcolor","border","capture","cellpadding","cellspacing","checked","cite","class","clear","color","cols","colspan","command","commandfor","controls","controlslist","coords","crossorigin","datetime","decoding","default","dir","disabled","disablepictureinpicture","disableremoteplayback","download","draggable","enctype","enterkeyhint","exportparts","face","for","headers","height","hidden","high","href","hreflang","id","inert","inputmode","integrity","ismap","kind","label","lang","list","loading","loop","low","max","maxlength","media","method","min","minlength","multiple","muted","name","nonce","noshade","novalidate","nowrap","open","optimum","part","pattern","placeholder","playsinline","popover","popovertarget","popovertargetaction","poster","preload","pubdate","radiogroup","readonly","rel","required","rev","reversed","role","rows","rowspan","spellcheck","scope","selected","shape","size","sizes","slot","span","srclang","start","src","srcset","step","style","summary","tabindex","title","translate","type","usemap","valign","value","width","wrap","xmlns"]),Ba=pe(["accent-height","accumulate","additive","alignment-baseline","amplitude","ascent","attributename","attributetype","azimuth","basefrequency","baseline-shift","begin","bias","by","class","clip","clippathunits","clip-path","clip-rule","color","color-interpolation","color-interpolation-filters","color-profile","color-rendering","cx","cy","d","dx","dy","diffuseconstant","direction","display","divisor","dominant-baseline","dur","edgemode","elevation","end","exponent","fill","fill-opacity","fill-rule","filter","filterunits","flood-color","flood-opacity","font-family","font-size","font-size-adjust","font-stretch","font-style","font-variant","font-weight","fx","fy","g1","g2","glyph-name","glyphref","gradientunits","gradienttransform","height","href","id","image-rendering","in","in2","intercept","k","k1","k2","k3","k4","kerning","keypoints","keysplines","keytimes","lang","lengthadjust","letter-spacing","kernelmatrix","kernelunitlength","lighting-color","local","marker-end","marker-mid","marker-start","markerheight","markerunits","markerwidth","maskcontentunits","maskunits","max","mask","mask-type","media","method","mode","min","name","numoctaves","offset","operator","opacity","order","orient","orientation","origin","overflow","paint-order","path","pathlength","patterncontentunits","patterntransform","patternunits","pointer-events","points","preservealpha","preserveaspectratio","primitiveunits","r","rx","ry","radius","refx","refy","repeatcount","repeatdur","restart","result","rotate","scale","seed","shape-rendering","slope","specularconstant","specularexponent","spreadmethod","startoffset","stddeviation","stitchtiles","stop-color","stop-opacity","stroke-dasharray","stroke-dashoffset","stroke-linecap","stroke-linejoin","stroke-miterlimit","stroke-opacity","stroke","stroke-width","style","surfacescale","systemlanguage","tabindex","tablevalues","targetx","targety","transform","transform-origin","text-anchor","text-decoration","text-orientation","text-rendering","textlength","type","u1","u2","unicode","values","vector-effect","viewbox","visibility","version","vert-adv-y","vert-origin-x","vert-origin-y","width","word-spacing","wrap","writing-mode","xchannelselector","ychannelselector","x","x1","x2","xmlns","y","y1","y2","z","zoomandpan"]),hi=pe(["accent","accentunder","align","bevelled","close","columnalign","columnlines","columnspacing","columnspan","denomalign","depth","dir","display","displaystyle","encoding","fence","frame","height","href","id","largeop","length","linethickness","lquote","lspace","mathbackground","mathcolor","mathsize","mathvariant","maxsize","minsize","movablelimits","notation","numalign","open","rowalign","rowlines","rowspacing","rowspan","rspace","rquote","scriptlevel","scriptminsize","scriptsizemultiplier","selection","separator","separators","stretchy","subscriptshift","supscriptshift","symmetric","voffset","width","xmlns"]),Ln=pe(["xlink:href","xml:id","xlink:title","xml:space","xmlns:xlink"]),Ic=fe(/{{[\w\W]*|^[\w\W]*}}/g),Dc=fe(/<%[\w\W]*|^[\w\W]*%>/g),Pc=fe(/\${[\w\W]*/g),Bc=fe(/^data-[\-\w.\u00B7-\uFFFF]+$/),zc=fe(/^aria-[\-\w]+$/),fi=fe(/^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i),Uc=fe(/^(?:\w+script|data):/i),jc=fe(/[\u0000-\u0020\u00A0\u1680\u180E\u2000-\u2029\u205F\u3000]/g),Fc=fe(/^html$/i),$c=fe(/^[a-z][.\w]*(-[.\w]+)+$/i),za=fe(/<[/\w!]/g),mi=fe(/<[/\w]/g),Hc=fe(/<\/no(script|embed|frames)/i),gi=fe(/\/>/i),le={element:1,attribute:2,text:3,cdataSection:4,entityReference:5,entityNode:6,processingInstruction:7,comment:8,document:9,documentType:10,documentFragment:11,notation:12},Gc=pe(G({},["style","script","xmp","iframe","noembed","noframes","plaintext","noscript"])),Vc=function(){return typeof window>"u"?null:window},qc=function(e,n){if(typeof e!="object"||typeof e.createPolicy!="function")return null;let a=null,r="data-tt-policy-suffix";n&&n.hasAttribute(r)&&(a=n.getAttribute(r));let i="dompurify"+(a?"#"+a:"");try{return e.createPolicy(i,{createHTML(s){return s},createScriptURL(s){return s}})}catch{return console.warn("TrustedTypes policy "+i+" could not be created."),null}},bi=function(){return{afterSanitizeAttributes:[],afterSanitizeElements:[],afterSanitizeShadowDOM:[],beforeSanitizeAttributes:[],beforeSanitizeElements:[],beforeSanitizeShadowDOM:[],uponSanitizeAttribute:[],uponSanitizeElement:[],uponSanitizeShadowNode:[]}},Qe=function(e,n,a,r){return _e(e,n)&&Dt(e[n])?G(r.base?Te(r.base):{},e[n],r.transform):a},Ua=function(e,n,a){let r=_e(e,n)?e[n]:void 0;return r&&typeof r=="object"?Te(r):a()};function Ei(){let t=arguments.length>0&&arguments[0]!==void 0?arguments[0]:Vc(),e=v=>Ei(v);if(e.version="3.4.17",e.removed=[],!t||!t.document||t.document.nodeType!==le.document||!t.Element)return e.isSupported=!1,e;let n=t.document,a=n,r=a.currentScript;t.DocumentFragment;let i=t.HTMLTemplateElement,s=t.Node,l=t.Element,c=t.NodeFilter;t.NamedNodeMap===void 0&&(t.NamedNodeMap||t.MozNamedAttrMap),t.HTMLFormElement;let d=t.DOMParser,p=t.trustedTypes,x=l.prototype,b=Ce(x,"cloneNode"),w=Ce(x,"remove"),h=Ce(x,"removeAttributeNode"),y=Ce(x,"nextSibling"),N=Ce(x,"childNodes"),I=Ce(x,"parentNode"),P=Ce(x,"shadowRoot"),H=Ce(x,"attributes"),B=s&&s.prototype?Ce(s.prototype,"nodeType"):null,q=s&&s.prototype?Ce(s.prototype,"nodeName"):null,X=s&&s.prototype?Ce(s.prototype,"ownerDocument"):null,ne=function(o){return B?B(o):o.nodeType},re=function(o){return q?q(o):o.nodeName},Re=Lc(x,"namespaceURI"),Se=function(o){return Re?Re(o):o.namespaceURI};if(typeof i=="function"){let v=n.createElement("template");v.content&&v.content.ownerDocument&&(n=v.content.ownerDocument)}let ae,ye="",Pe,ke=!1,Me=0,_=function(){if(Me>0)throw Ge('A configured TRUSTED_TYPES_POLICY callback (createHTML or createScriptURL) must not call DOMPurify.sanitize, as that causes infinite recursion. Do not pass a policy whose callbacks wrap DOMPurify as TRUSTED_TYPES_POLICY; see the "DOMPurify and Trusted Types" section of the README.')},S=function(o){_(),Me++;try{return ae.createHTML(o)}finally{Me--}},R=function(o){_(),Me++;try{return ae.createScriptURL(o)}finally{Me--}},j=function(){return ke||(Pe=qc(p,r),ke=!0),Pe},E=n,L=E.implementation,D=E.createNodeIterator,W=E.createDocumentFragment,z=E.getElementsByTagName,Q=a.importNode,K=bi();e.isSupported=typeof yi=="function"&&typeof I=="function"&&L&&L.createHTMLDocument!==void 0;let an=Ic,rn=Dc,$n=Pc,Hn=Bc,Gn=zc,Vn=Uc,nt=jc,sn=$c,Ee=fi,Z=null,at=G({},[...ui,...Ia,...Da,...Pa,...di]),T=null,bt=G({},[...pi,...Ba,...hi,...Ln]),Y=Object.seal(It(null,{tagNameCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},attributeNameCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},allowCustomizedBuiltInElements:{writable:!0,configurable:!1,enumerable:!0,value:!1}})),V=null,rt=null,me=Object.seal(It(null,{tagCheck:{writable:!0,configurable:!1,enumerable:!0,value:null},attributeCheck:{writable:!0,configurable:!1,enumerable:!0,value:null}})),yt=!0,st=!0,A=!1,k=!0,M=!1,F=!0,ee=!1,Ae=!1,vt=null,xt=null,qn=!1,_t=!1,on=!1,ln=!1,ar=!0,rr=!1,sr="user-content-",Kn=!0,Wn=!1,it=null,wt={},ot=null,ir=G({},["annotation-xml","audio","colgroup","desc","foreignobject","head","iframe","math","mi","mn","mo","ms","mtext","noembed","noframes","noscript","plaintext","script","selectedcontent","style","svg","template","thead","title","video","xmp"]),or=null,lr=G({},["audio","video","img","source","image","track"]),cr=null,ur=G({},["alt","class","for","id","label","name","pattern","placeholder","role","summary","title","value","style","xmlns"]),cn="http://www.w3.org/1998/Math/MathML",un="http://www.w3.org/2000/svg",Be="http://www.w3.org/1999/xhtml",Et=Be,Yn=!1,Zn=null,so=G({},[cn,un,Be],Oa),dr=pe(["mi","mo","mn","ms","mtext"]),Jn=G({},dr),pr=pe(["annotation-xml"]),Xn=G({},pr),io=G({},["title","style","font","a","script"]),Bt=null,oo=["application/xhtml+xml","text/html"],lo="text/html",se=null,At=null,co=n.createElement("form"),hr=function(o){return o instanceof RegExp||o instanceof Function},Qn=function(){let o=arguments.length>0&&arguments[0]!==void 0?arguments[0]:{};if(At&&At===o)return;(!o||typeof o!="object")&&(o={}),o=Te(o),Bt=oo.indexOf(o.PARSER_MEDIA_TYPE)===-1?lo:o.PARSER_MEDIA_TYPE,se=Bt==="application/xhtml+xml"?Oa:pt,Z=Qe(o,"ALLOWED_TAGS",at,{transform:se}),T=Qe(o,"ALLOWED_ATTR",bt,{transform:se}),Zn=Qe(o,"ALLOWED_NAMESPACES",so,{transform:Oa}),cr=Qe(o,"ADD_URI_SAFE_ATTR",ur,{transform:se,base:ur}),or=Qe(o,"ADD_DATA_URI_TAGS",lr,{transform:se,base:lr}),ot=Qe(o,"FORBID_CONTENTS",ir,{transform:se}),V=Qe(o,"FORBID_TAGS",Te({}),{transform:se}),rt=Qe(o,"FORBID_ATTR",Te({}),{transform:se}),wt=_e(o,"USE_PROFILES")?o.USE_PROFILES&&typeof o.USE_PROFILES=="object"?Te(o.USE_PROFILES):o.USE_PROFILES:!1,yt=o.ALLOW_ARIA_ATTR!==!1,st=o.ALLOW_DATA_ATTR!==!1,A=o.ALLOW_UNKNOWN_PROTOCOLS||!1,k=o.ALLOW_SELF_CLOSE_IN_ATTR!==!1,M=o.SAFE_FOR_TEMPLATES||!1,F=o.SAFE_FOR_XML!==!1,ee=o.WHOLE_DOCUMENT||!1,_t=o.RETURN_DOM||!1,on=o.RETURN_DOM_FRAGMENT||!1,ln=o.RETURN_TRUSTED_TYPE||!1,qn=o.FORCE_BODY||!1,ar=o.SANITIZE_DOM!==!1,rr=o.SANITIZE_NAMED_PROPS||!1,Kn=o.KEEP_CONTENT!==!1,Wn=o.IN_PLACE||!1,Ee=Rc(o.ALLOWED_URI_REGEXP)?o.ALLOWED_URI_REGEXP:fi,Et=typeof o.NAMESPACE=="string"?o.NAMESPACE:Be,Jn=Ua(o,"MATHML_TEXT_INTEGRATION_POINTS",()=>G({},dr)),Xn=Ua(o,"HTML_INTEGRATION_POINTS",()=>G({},pr));let u=Ua(o,"CUSTOM_ELEMENT_HANDLING",()=>It(null));if(Y=It(null),_e(u,"tagNameCheck")&&hr(u.tagNameCheck)&&(Y.tagNameCheck=u.tagNameCheck),_e(u,"attributeNameCheck")&&hr(u.attributeNameCheck)&&(Y.attributeNameCheck=u.attributeNameCheck),_e(u,"allowCustomizedBuiltInElements")&&typeof u.allowCustomizedBuiltInElements=="boolean"&&(Y.allowCustomizedBuiltInElements=u.allowCustomizedBuiltInElements),fe(Y),M&&(st=!1),on&&(_t=!0),wt&&(Z=G({},di),T=It(null),wt.html===!0&&(G(Z,ui),G(T,pi)),wt.svg===!0&&(G(Z,Ia),G(T,Ba),G(T,Ln)),wt.svgFilters===!0&&(G(Z,Da),G(T,Ba),G(T,Ln)),wt.mathMl===!0&&(G(Z,Pa),G(T,hi),G(T,Ln))),me.tagCheck=null,me.attributeCheck=null,_e(o,"ADD_TAGS")&&(typeof o.ADD_TAGS=="function"?me.tagCheck=o.ADD_TAGS:Dt(o.ADD_TAGS)&&(Z===at&&(Z=Te(Z)),G(Z,o.ADD_TAGS,se))),_e(o,"ADD_ATTR")&&(typeof o.ADD_ATTR=="function"?me.attributeCheck=o.ADD_ATTR:Dt(o.ADD_ATTR)&&(T===bt&&(T=Te(T)),G(T,o.ADD_ATTR,se))),_e(o,"ADD_FORBID_CONTENTS")&&Dt(o.ADD_FORBID_CONTENTS)&&(ot===ir&&(ot=Te(ot)),G(ot,o.ADD_FORBID_CONTENTS,se)),Kn&&(Z["#text"]=!0),ee&&G(Z,["html","head","body"]),Z.table&&(G(Z,["tbody"]),delete V.tbody),o.TRUSTED_TYPES_POLICY){if(typeof o.TRUSTED_TYPES_POLICY.createHTML!="function")throw Ge('TRUSTED_TYPES_POLICY configuration option must provide a "createHTML" hook.');if(typeof o.TRUSTED_TYPES_POLICY.createScriptURL!="function")throw Ge('TRUSTED_TYPES_POLICY configuration option must provide a "createScriptURL" hook.');let f=ae;ae=o.TRUSTED_TYPES_POLICY;try{ye=S("")}catch(m){throw ae=f,m}}else o.TRUSTED_TYPES_POLICY===null?(ae=void 0,ye=""):(ae===void 0&&(ae=j()),ae&&typeof ye=="string"&&(ye=S("")));pe&&pe(o),At=o},fr=G({},[...Ia,...Da,...Mc]),mr=G({},[...Pa,...Oc]),uo=function(o,u,f){return u.namespaceURI===Be?o==="svg":u.namespaceURI===cn?o==="svg"&&(f==="annotation-xml"||Jn[f]):!!fr[o]},po=function(o,u,f){return u.namespaceURI===Be?o==="math":u.namespaceURI===un?o==="math"&&Xn[f]:!!mr[o]},ho=function(o,u,f){return u.namespaceURI===un&&!Xn[f]||u.namespaceURI===cn&&!Jn[f]?!1:!mr[o]&&(io[o]||!fr[o])},fo=function(o){let u=Se(o),f=pt(re(o)),m=I(o),C,O;return m&&ne(m)===le.element?(C={namespaceURI:Se(m)},O=pt(re(m))):(C={namespaceURI:Et},O="template"),Zn[u]?u===un?uo(f,C,O):u===cn?po(f,C,O):u===Be?ho(f,C,O):!!(Bt==="application/xhtml+xml"&&Zn[u]):!1},Ye=function(o){Wt(e.removed,{element:o});try{I(o).removeChild(o)}catch{if(w(o),!I(o))throw Ge("a node selected for removal could not be detached from its tree and cannot be safely returned; refusing to sanitize in place")}},gr=function(o,u,f){try{h(o,u)}catch{try{o.removeAttribute(f)}catch{}}},ea=function(o){na(o);let u=N(o);u&&He(Ec(u),m=>{try{w(m)}catch{}});let f=ne(o)===le.element?H(o):null;if(f)for(let m=f.length-1;m>=0;--m){let C=f[m],O=C&&C.name;typeof O=="string"&&gr(o,C,O)}},Tt=function(o,u,f){if(!f)try{f=u.getAttributeNode(o)}catch{f=null}Wt(e.removed,{attribute:f||null,from:u});try{f?h(u,f):u.removeAttribute(o)}catch{try{u.removeAttribute(o)}catch{}}if(o==="is")if(_t||on)try{Ye(u)}catch{}else try{u.setAttribute(o,"")}catch{}},br=function(o){let u=H(o);if(u)for(let f=u.length-1;f>=0;--f){let m=u[f],C=m&&m.name;typeof C!="string"||T[se(C)]||gr(o,m,C)}},ta=function(o,u){let f=arguments.length>2&&arguments[2]!==void 0?arguments[2]:!1,m=[o];for(;m.length>0;){let C=m.pop();if(u(C)===!1)continue;if(f&&ne(C)===le.element){let U=P(C);Ze(U)&&m.push(U)}let O=N(C);if(O)for(let U=O.length-1;U>=0;--U)m.push(O[U])}},na=function(o){ta(o,u=>{ne(u)===le.element&&br(u)})},aa=function(o){let u=[];return ta(o,f=>{u.push(f)},!0),u},mo=function(o,u){let f=Ra();He(aa(o),m=>{ne(m)===le.element&&Ma(f,m)}),He(u,m=>{ne(m)===le.element&&!Yt(f,m)&&br(m)})},yr=function(o,u){let f=!1;return He(e.removed,m=>{m.element&&(f=f||m.element===o,na(m.element))}),mo(o,u),f},go=8,bo=function(o,u){let f=it,m=null,C=()=>(m||(m=Ra(),He(u,O=>{Ma(m,O)})),m);for(let O=0;;O++){let U=aa(o),ce=[o],ze=!1;if(He(U,be=>{ne(be)===le.documentFragment?Wt(ce,be):!ze&&!Yt(f,be)&&(ze=Yt(C(),be))}),!ze)return;if(O>=go)throw Ge("the tree kept changing during in-place sanitization; refusing to return it");He(ce,(be,ve)=>{yo(be,ve>0,o,C())})}},yo=function(o,u,f,m){let C=ra(o),O;for(;O=C.nextNode();)!Yt(m,O)||Yt(it,O)||(u&&Oe(K.uponSanitizeShadowNode,O,null),ia(O,f),oa(O,f),Ze(O.content)&&Ut(O.content))},vo=function(o){it&&Ma(it,o)},vr=function(o,u){return F?o==="patchsrc"?!0:o==="for"&&u!=="label"&&u!=="output":!1},xo=function(o){F&&ta(o,u=>{let f=ne(u);if(f===le.processingInstruction||f===le.comment&&he(mi,u.data)){try{w(u)}catch{}return!1}if(f===le.element){let m=u,C=se(re(u));try{m.hasAttribute&&m.hasAttribute("patchsrc")&&m.removeAttribute("patchsrc"),m.hasAttribute&&m.hasAttribute("for")&&vr("for",C)&&m.removeAttribute("for")}catch{}}return!0})},xr=function(o){let u=null,f=null;if(qn)o="<remove></remove>"+o;else{let O=ii(o,/^[\r\n\t ]+/);f=O&&O[0]}Bt==="application/xhtml+xml"&&Et===Be&&(o='<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body>'+o+"</body></html>");let m=ae?S(o):o;if(Et===Be)try{u=new d().parseFromString(m,Bt)}catch{}if(!u||!u.documentElement){u=L.createDocument(Et,"template",null);try{u.documentElement.innerHTML=Yn?ye:m}catch{}}let C=u.body||u.documentElement;return o&&f&&C.insertBefore(n.createTextNode(f),C.childNodes[0]||null),Et===Be?z.call(u,ee?"html":"body")[0]:ee?u.documentElement:C},ra=function(o){let u=X?X(o):o.ownerDocument;return D.call(u||o,o,c.SHOW_ELEMENT|c.SHOW_COMMENT|c.SHOW_TEXT|c.SHOW_PROCESSING_INSTRUCTION|c.SHOW_CDATA_SECTION,null)},dn=function(o){return o=Zt(o,an," "),o=Zt(o,rn," "),o=Zt(o,$n," "),o},sa=function(o){var u;_r(o);let f=(u=o.querySelectorAll)===null||u===void 0?void 0:u.call(o,"template");f&&He(f,m=>{Ze(m.content)&&sa(m.content)})},_r=function(o){o.normalize();let u=X?X(o):o.ownerDocument,f=D.call(u||o,o,c.SHOW_TEXT|c.SHOW_COMMENT|c.SHOW_CDATA_SECTION|c.SHOW_PROCESSING_INSTRUCTION,null),m=f.nextNode();for(;m;)m.data=dn(m.data),m=f.nextNode()},pn=function(o){let u=q?q(o):null;return typeof u!="string"||se(u)!=="form"?!1:typeof o.nodeName!="string"||typeof o.textContent!="string"||typeof o.removeChild!="function"||o.attributes!==H(o)||typeof o.removeAttribute!="function"||typeof o.removeAttributeNode!="function"||typeof o.getAttributeNode!="function"||typeof o.setAttribute!="function"||typeof o.namespaceURI!="string"||typeof o.insertBefore!="function"||typeof o.hasChildNodes!="function"||o.nodeType!==B(o)||o.childNodes!==N(o)},Ze=function(o){if(!B||typeof o!="object"||o===null)return!1;try{return B(o)===le.documentFragment}catch{return!1}},zt=function(o){if(!B||typeof o!="object"||o===null)return!1;try{return typeof B(o)=="number"}catch{return!1}};function Oe(v,o,u){v.length!==0&&He(v,f=>{f.call(e,o,u,At)})}let _o=function(o,u){return!!(F&&o.hasChildNodes()&&!zt(o.firstElementChild)&&he(za,o.textContent)&&he(za,o.innerHTML)||F&&Gc[u]&&ne(o)===le.element&&Se(o)===Be&&(zt(o.firstElementChild)||typeof o.textContent=="string"&&he(za,o.textContent))||o.nodeType===le.processingInstruction||F&&o.nodeType===le.comment&&he(mi,o.data))},hn=function(o,u){if(o instanceof RegExp)return he(o,u);if(o instanceof Function){for(var f=arguments.length,m=new Array(f>2?f-2:0),C=2;C<f;C++)m[C-2]=arguments[C];return!!o(u,...m)}return!1},wo=function(o,u,f){if(!V[u]&&Ar(u)&&hn(Y.tagNameCheck,u))return!1;if(Kn&&!ot[u]&&!ot[pt(u)]){let m=I(o),C=N(o);if(C&&m){let O=C.length;for(let U=O-1;U>=0;--U){let ce=o===f?b(C[U],!0):C[U];m.insertBefore(ce,y(o))}}}return Ye(o),!0},wr=function(o,u,f,m){return o.length===0?u:u===f||u===m?Te(u):u},St=function(o,u){return o===u||I(o)!==null?!1:(Wn&&na(o),!0)},ia=function(o,u){if(vo(o),Oe(K.beforeSanitizeElements,o,null),St(o,u))return!0;if(pn(o))return Ye(o),!0;let f=se(re(o));if(Z=wr(K.uponSanitizeElement,Z,at,vt),Oe(K.uponSanitizeElement,o,{tagName:f,allowedTags:Z}),St(o,u))return!0;if(_o(o,f))return Ye(o),!0;if(V[f]||!(me.tagCheck instanceof Function&&me.tagCheck(f))&&!Z[f]){let m=wo(o,f,u);return m===!1&&(Oe(K.afterSanitizeElements,o,null),St(o,u))?!0:m}if(ne(o)===le.element&&!fo(o)||(f==="noscript"||f==="noembed"||f==="noframes")&&he(Hc,o.innerHTML))return Ye(o),!0;if(M&&o.nodeType===le.text){let m=dn(o.textContent);o.textContent!==m&&(Wt(e.removed,{element:o.cloneNode()}),o.textContent=m)}return Oe(K.afterSanitizeElements,o,null),St(o,u)},Er=function(o,u,f){if(rt[u]||vr(u,o)||ar&&(u==="id"||u==="name")&&(f in n||f in co))return!1;let m=T[u]||me.attributeCheck instanceof Function&&me.attributeCheck(u,o);return st&&he(Hn,u)||yt&&he(Gn,u)?!0:m?cr[u]||he(Ee,Zt(f,nt,""))||(u==="src"||u==="xlink:href"||u==="href")&&o!=="script"&&oi(f,"data:")===0&&or[o]||A&&!he(Vn,Zt(f,nt,""))?!0:!f:Ar(o)&&hn(Y.tagNameCheck,o)&&hn(Y.attributeNameCheck,u,o)||u==="is"&&Y.allowCustomizedBuiltInElements&&hn(Y.tagNameCheck,f)},Eo=G({},["annotation-xml","color-profile","font-face","font-face-format","font-face-name","font-face-src","font-face-uri","missing-glyph"]),Ar=function(o){return!Eo[pt(o)]&&he(sn,o)},Ao=function(o,u,f,m){if(ae&&typeof p=="object"&&typeof p.getAttributeType=="function"&&!f)switch(p.getAttributeType(o,u)){case"TrustedHTML":return S(m);case"TrustedScriptURL":return R(m)}return m},To=function(o,u,f,m){try{return f?o.setAttributeNS(f,u,m):o.setAttribute(u,m),pn(o)?(Ye(o),!1):!0}catch{return Tt(u,o),!1}},Tr=function(o,u){return F&&he(/((--!?|])>)|<\/(style|script|title|xmp|textarea|noscript|iframe|noembed|noframes)/i,u)?!0:pt(o)==="attributename"&&ii(u,"href")!==null},oa=function(o,u){if(Oe(K.beforeSanitizeAttributes,o,null),St(o,u))return;let f=o.attributes;if(!f||pn(o))return;T=wr(K.uponSanitizeAttribute,T,bt,xt);let m={attrName:"",attrValue:"",keepAttr:!0,allowedAttributes:T,forceKeepAttr:void 0},C=f.length,O=se(o.nodeName);for(;C--;){let U=f[C],ce=U.name,ze=U.namespaceURI,be=U.value,ve=se(ce),kt=be,xe=ce==="value"?kt:Tc(kt),Sr=!1;if(m.attrName=ve,m.attrValue=xe,m.keepAttr=!0,m.forceKeepAttr=void 0,Oe(K.uponSanitizeAttribute,o,m),xe=m.attrValue,rr&&(ve==="id"||ve==="name")&&oi(xe,sr)!==0&&(Tt(ce,o,U),xe=sr+xe,Sr=!0),Tr(ce,xe)){Tt(ce,o,U);continue}if(!m.forceKeepAttr){if(!m.keepAttr){Tt(ce,o,U);continue}if(!k&&he(gi,xe)){Tt(ce,o,U);continue}if(M&&(xe=dn(xe)),!Er(O,ve,xe)){Tt(ce,o,U);continue}xe=Ao(O,ve,ze,xe),xe!==kt&&To(o,ce,ze,xe)&&Sr&&si(e.removed)}}Oe(K.afterSanitizeAttributes,o,null),St(o,u)},Ut=function(o){let u=null,f=ra(o);for(Oe(K.beforeSanitizeShadowDOM,o,null);u=f.nextNode();)if(Oe(K.uponSanitizeShadowNode,u,null),ia(u,o),oa(u,o),Ze(u.content)&&Ut(u.content),ne(u)===le.element){let m=P(u);Ze(m)&&(la(m),Ut(m))}M&&_r(o),Oe(K.afterSanitizeShadowDOM,o,null)},la=function(o){let u=[{node:o,shadow:null}];for(;u.length>0;){let f=u.pop();if(f.shadow){Ut(f.shadow);continue}let m=f.node,C=ne(m)===le.element,O=N(m);if(O)for(let U=O.length-1;U>=0;--U)u.push({node:O[U],shadow:null});if(C){let U=q?q(m):null;if(typeof U=="string"&&se(U)==="template"){let ce=m.content;Ze(ce)&&u.push({node:ce,shadow:null})}}if(C){let U=P(m);Ze(U)&&u.push({node:null,shadow:U},{node:U,shadow:null})}}};return e.sanitize=function(v){let o=arguments.length>1&&arguments[1]!==void 0?arguments[1]:{},u=null,f=null,m=null,C=null;if(Yn=!v,Yn&&(v="<!-->"),typeof v!="string"&&!zt(v)&&(v=Cc(v),typeof v!="string"))throw Ge("dirty is not a string, aborting");if(!e.isSupported)return v;Ae?(Z=vt,T=xt):Qn(o),(K.uponSanitizeElement.length>0||K.uponSanitizeAttribute.length>0)&&(Z=Te(Z)),K.uponSanitizeAttribute.length>0&&(T=Te(T)),e.removed=[];let O=Wn&&typeof v!="string"&&zt(v),U=[],ce=it;if(O){xo(v);let ve=re(v);if(typeof ve=="string"){let kt=se(ve);if(!Z[kt]||V[kt])throw ea(v),Ge("root node is forbidden and cannot be sanitized in-place")}if(pn(v))throw ea(v),Ge("root node is clobbered and cannot be sanitized in-place");U=aa(v),it=Ra()}else if(zt(v))u=xr("<!---->"),f=u.ownerDocument.importNode(v,!0),f.nodeType===le.element&&f.nodeName==="BODY"||f.nodeName==="HTML"?u=f:u.appendChild(f),la(u);else{if(!_t&&!M&&!ee&&v.indexOf("<")===-1)return ae&&ln?S(v):v;if(u=xr(v),!u)return _t?null:ln?ye:""}u&&qn&&Ye(u.firstChild);let ze=O?v:u;try{O&&la(v);let ve=ra(ze);for(;m=ve.nextNode();)ia(m,ze),oa(m,ze),Ze(m.content)&&Ut(m.content);O&&bo(v,U)}catch(ve){throw O&&(ea(v),yr(v,U)),ve}finally{it=ce}if(O){if(yr(v,U))throw Ge("a node selected for removal could not be safely returned; refusing to sanitize in place");return M&&sa(v),v}if(_t){if(M&&sa(u),on)for(C=W.call(u.ownerDocument);u.firstChild;)C.appendChild(u.firstChild);else C=u;return(T.shadowroot||T.shadowrootmode)&&(C=Q.call(a,C,!0)),C}let be=ee?u.outerHTML:u.innerHTML;return ee&&Z["!doctype"]&&u.ownerDocument&&u.ownerDocument.doctype&&u.ownerDocument.doctype.name&&he(Fc,u.ownerDocument.doctype.name)&&(be="<!DOCTYPE "+u.ownerDocument.doctype.name+`>
`+be),M&&(be=dn(be)),ae&&ln?S(be):be},e.setConfig=function(){let v=arguments.length>0&&arguments[0]!==void 0?arguments[0]:{};Qn(v),Ae=!0,vt=Z,xt=T},e.clearConfig=function(){At=null,Ae=!1,vt=null,xt=null,ae=Pe,ye=""},e.isValidAttribute=function(v,o,u){At||Qn({});let f=se(v),m=se(o);return typeof u=="string"&&(Tr(o,u)||!k&&he(gi,u))?!1:Er(f,m,u)},e.addHook=function(v,o){typeof o=="function"&&_e(K,v)&&Wt(K[v],o)},e.removeHook=function(v,o){if(_e(K,v)){if(o!==void 0){let u=wc(K[v],o);return u===-1?void 0:Ac(K[v],u,1)[0]}return si(K[v])}},e.removeHooks=function(v){_e(K,v)&&(K[v]=[])},e.removeAllHooks=function(){K=bi()},e}var Rn=Ei();var Ai="vitrine",Jd=Object.freeze(["a","abbr","b","blockquote","br","caption","code","col","colgroup","dd","del","details","div","dl","dt","em","figcaption","figure","h1","h2","h3","h4","h5","h6","hr","i","img","input","ins","kbd","li","mark","ol","p","pre","q","s","samp","small","span","strong","sub","summary","sup","table","tbody","td","tfoot","th","thead","tr","u","ul","var"]),Xd=Object.freeze(["align","alt","checked","class","colspan","dir","disabled","height","href","lang","open","rowspan","span","src","start","title","type","width"]);var Xt;function $a(){if(Xt!==void 0)return Xt;Xt=null;let t=globalThis.trustedTypes;if(t&&typeof t.createPolicy=="function")try{Xt=t.createPolicy(Ai,{createHTML:e=>e,createScriptURL:e=>e})}catch{console.warn(`[vitrine] Could not create the "${Ai}" Trusted Types policy. Add it to your CSP "trusted-types" directive.`)}return Xt??null}function Kc(t){let e=document.createDocumentFragment();return e.append(document.createTextNode(String(t))),e}var ht;function Wc(){if(ht!==void 0)return ht;ht=!1;try{if(!Rn.isSupported)return!1;let t=Rn.sanitize('<b>1</b><script>1<\/script><a href="javascript:1">a</a>',{RETURN_DOM_FRAGMENT:!0,...$a()?{TRUSTED_TYPES_POLICY:$a()}:{}});ht=t instanceof DocumentFragment&&t.querySelector("b")!==null&&t.querySelector("script")===null&&!t.querySelector("a")?.hasAttribute("href")}catch{ht=!1}return ht||console.warn("[vitrine] HTML sanitizer unavailable: rich content is shown as plain text."),ht}var Yc=/^(?:hljs-[\w-]{1,40}|[a-z]{1,20}_{1,2})$/;function Ti(t){if(!Wc())return Kc(t);let e=$a(),n={ALLOWED_TAGS:["span"],ALLOWED_ATTR:["class"],ALLOW_DATA_ATTR:!1,ALLOW_ARIA_ATTR:!1,RETURN_DOM_FRAGMENT:!0,KEEP_CONTENT:!0};e&&(n.TRUSTED_TYPES_POLICY=e);let a=Rn.sanitize(String(t),n);for(let r of Array.from(a.querySelectorAll("[class]"))){let i=Array.from(r.classList).filter(s=>Yc.test(s));i.length?r.setAttribute("class",i.join(" ")):r.removeAttribute("class")}return a}var Qd=Object.freeze(["script","style","iframe","object","embed","form","input","button","textarea","select","link","meta","base","img","image","video","audio","source","animate","animateMotion","animateTransform","set","feImage"]);var Zc={bash:Hs,diff:Gs,javascript:Ys,json:Zs,markdown:Js,plaintext:Xs,python:Qs,shell:ei,xml:ti,yaml:ni};for(let[t,e]of Object.entries(Zc))je.registerLanguage(t,e);je.configure({ignoreUnescapedHTML:!0,throwUnescapedHTML:!1});var Jc=4e3,ft=null,Si=new Map,Xc=1e4;function ki(t){if(typeof t!="string")return null;let e=t.trim().toLowerCase();if(!e||e.length>40)return null;if(Object.prototype.hasOwnProperty.call(Nn,e))return e;if(!ft){ft=new Map;for(let[n,a]of Object.entries(Nn))for(let r of a.split(" "))r&&!ft.has(r)&&ft.set(r,n);ft.set("text","plaintext"),ft.set("plain","plaintext")}return ft.get(e)??null}function Mn(t){return!!je.getLanguage(t)}function Ni(t){if(Mn(t))return Promise.resolve(!0);if(!Object.prototype.hasOwnProperty.call(Nn,t))return Promise.resolve(!1);let e=Si.get(t);if(e)return e;let n=Qc(t);return Si.set(t,n),n}async function Qc(t){let e=J().languagesUrl||is();if(!e)return!1;try{let n=new URL(`${t}.js`,new URL(e.endsWith("/")?e:`${e}/`,document.baseURI));if(n.protocol!=="https:"&&n.protocol!=="http:")return!1;let a=await import(n.href);return typeof a.default!="function"?!1:(je.registerLanguage(t,a.default),!0)}catch(n){return console.warn(`[vitrine] Could not load the "${t}" language.`,n),!1}}function Ci(t){let e=je.listLanguages().filter(a=>a!=="plaintext"),n=je.highlightAuto(t.slice(0,Jc),e);return n.language&&n.relevance>=3?n.language:"plaintext"}function eu(t){for(let e=0;e<t.length;){let n=t.indexOf(`
`,e),a=n===-1?t.length:n;if(a-e>Xc)return!0;e=a+1}return!1}function Li(t,e){if(e==="plaintext"||!Mn(e)||eu(t)){let a=document.createDocumentFragment();return a.append(document.createTextNode(t)),a}let n=je.highlight(t,{language:e,ignoreIllegals:!0});return Ti(n.value)}function Ri(t){let e=[],n=[],a=document.createDocumentFragment(),r=a,i=()=>{e.push(a),a=document.createDocumentFragment(),r=a;for(let l of n){let c=l.cloneNode(!1);r.appendChild(c),r=c}},s=l=>{if(l.nodeType===Node.TEXT_NODE){(l.nodeValue??"").split(`
`).forEach((p,x)=>{x>0&&i(),p&&r.appendChild(document.createTextNode(p))});return}if(l.nodeType!==Node.ELEMENT_NODE)return;let c=l;r.appendChild(c.cloneNode(!1)),r=r.lastChild,n.push(c);for(let d of Array.from(c.childNodes))s(d);n.pop(),r=r.parentNode};for(let l of Array.from(t.childNodes))s(l);return e.push(a),e}var tu=1e3,Mi=200;function nu(t){let e=[],n=[];for(let a of t)a.startsWith("@@")?(e.push("hunk"),n.push(a)):/^(?:\+\+\+|---)(?: |$)|^diff |^index /.test(a)?(e.push("meta"),n.push(a)):a.startsWith("+")?(e.push("added"),n.push(a.slice(1))):a.startsWith("-")?(e.push("removed"),n.push(a.slice(1))):(e.push("context"),n.push(a.startsWith(" ")?a.slice(1):a));return{kinds:e,code:n}}function On(t,e){let a=(t.endsWith(`
`)&&!e.trailingNewline?t.slice(0,-1):t).split(`
`),r=null;if(e.diff){let P=nu(a);r=P.kinds,a=P.code}let i=a.join(`
`),s=i.length>e.highlightLimit,l=s||e.language==="plaintext",c=l?null:Ri(Li(i,e.language)),d=l?i.split(`
`):null,p=c?c.length:d.length,x=e.startLine+p-1,b=Math.max(String(e.startLine).length,String(x).length),w=g("pre",{class:"code",part:"code"});w.style.setProperty("--_digits",String(b));let h=P=>{let H=e.startLine+P,B=r?.[P],q=g("span",{class:"line",part:"line",attrs:{"data-line":H}});if(e.highlightRanges.length&&Cr(H,e.highlightRanges)&&(q.classList.add("highlighted"),q.setAttribute("part","line line-highlighted")),B&&B!=="context"&&q.classList.add(B),e.lineNumbers&&q.append(g("span",{class:"gutter",part:"gutter line-number",attrs:{"aria-hidden":"true","data-n":H}})),r){let ne=B==="added"?e.diffLabels?.added:B==="removed"?e.diffLabels?.removed:"";q.append(g("span",{class:"sign"},ne?g("span",{class:"sr-only",text:`${ne}: `}):null))}let X=g("span",{class:"content"});return c?X.append(c[P]):d?.[P]&&X.append(d[P]),P<p-1&&X.append(`
`),q.append(X),q},y=(P,H,B)=>{let q=document.createDocumentFragment();for(let X=H;X<B;X+=1)q.appendChild(h(X));P.appendChild(q)},N=document.createDocumentFragment();if(e.chunk!==!1&&p>tu)for(let P=0;P<p;P+=Mi){let H=Math.min(p,P+Mi),B=g("span",{class:"chunk",attrs:{"data-first":e.startLine+P,"data-count":H-P}});B.style.setProperty("--_chunk-lines",String(H-P)),N.append(B),P===0?y(B,P,H):(B.setAttribute("data-pending",""),ms(B,()=>{B.removeAttribute("data-pending"),y(B,P,H)}))}else y(N,0,p);return w.append(N),{element:g("div",{class:"code-view"},w),code:w,lineCount:p,highlightSkipped:s}}function Ha(t){t&&(t.closest(".chunk")?.classList.add("revealed"),t.scrollIntoView({block:"nearest",inline:"nearest"}))}var In=class{constructor(e){this.steps=[{value:e,start:0,end:0}],this.index=0,this.lastKind="",this.lastTime=0,this.listeners=new Set}get canUndo(){return this.index>0}get canRedo(){return this.index<this.steps.length-1}get current(){return this.steps[this.index]}record(e,n){if(e.value===this.current.value)return;let a=Date.now(),i=(n==="insertText"||n.startsWith("delete"))&&n===this.lastKind&&a-this.lastTime<600&&!this.canRedo;this.steps.length=this.index+1,i&&this.index>0?this.steps[this.index]=e:(this.steps.push(e),this.index+=1),this.lastKind=n,this.lastTime=a,this.trim(),this.notify()}undo(){return this.canUndo?(this.index-=1,this.lastKind="",this.notify(),this.current):null}redo(){return this.canRedo?(this.index+=1,this.lastKind="",this.notify(),this.current):null}trim(){let e=this.steps.reduce((n,a)=>n+a.value.length,0);for(;this.steps.length>1&&(this.steps.length>300||e>2e7)&&this.index>0;)e-=this.steps.shift().value.length,this.index-=1}subscribe(e){return this.listeners.add(e),()=>this.listeners.delete(e)}notify(){for(let e of this.listeners)e()}};var au=6e4,ru=250,Dn="  ",et=class{constructor(e){this.options=e,this.text=e.text,this.tabReleased=!1,this.changedSinceFocus=!1,this.timer=void 0,this.textarea=g("textarea",{class:"editor-input",part:"editor",attrs:{"aria-label":e.label,placeholder:e.placeholder??null,spellcheck:"false",autocapitalize:"off",autocomplete:"off",autocorrect:"off",wrap:e.wrap?"soft":"off","data-focus-key":"editor"}}),this.textarea.value=e.text,this.history=e.history&&e.history.current.value===e.text?e.history:new In(e.text),this.layer=this.buildLayer(e.text),this.element=g("div",{class:e.wrap?"editor wrap":"editor"},this.layer,this.textarea),this.textarea.addEventListener("input",n=>this.onInput(n.inputType||"other")),this.textarea.addEventListener("beforeinput",n=>{(n.inputType==="historyUndo"||n.inputType==="historyRedo")&&(n.preventDefault(),n.inputType==="historyUndo"?this.undo():this.redo())}),this.textarea.addEventListener("keydown",n=>this.onKeyDown(n)),this.textarea.addEventListener("focus",()=>{this.changedSinceFocus=!1}),this.textarea.addEventListener("blur",()=>{this.changedSinceFocus&&e.onChange?.(this.text)})}buildLayer(e){let n=On(e,{language:this.options.language,lineNumbers:this.options.lineNumbers,startLine:1,highlightRanges:this.options.highlightRanges??[],diff:!1,highlightLimit:this.options.highlightLimit,trailingNewline:!0,chunk:!1});return n.element.classList.add("editor-layer"),n.element.setAttribute("aria-hidden","true"),n.element}refresh(){clearTimeout(this.timer);let e=this.buildLayer(this.text);this.layer.replaceWith(e),this.layer=e,this.element.classList.remove("pending"),this.align()}align(){let e=this.layer.querySelector(".gutter"),n=e?e.getBoundingClientRect().width:0;this.element.style.setProperty("--_editor-gutter",`${n}px`)}setHighlightRanges(e){this.options.highlightRanges=e,this.refresh()}onInput(e){this.text=this.textarea.value.replace(/\r\n?/g,`
`),this.changedSinceFocus=!0,this.history.record({value:this.text,start:this.textarea.selectionStart,end:this.textarea.selectionEnd},e),this.text.length<=au?this.refresh():(this.element.classList.add("pending"),clearTimeout(this.timer),this.timer=setTimeout(()=>this.refresh(),ru)),this.options.onInput(this.text)}onKeyDown(e){let n=e.ctrlKey||e.metaKey,a=e.key.toLowerCase();if(n&&!e.altKey&&(a==="z"||a==="y")){e.preventDefault(),a==="y"||e.shiftKey?this.redo():this.undo();return}if(e.key==="Escape"){this.tabReleased=!0;return}if(e.key==="Tab"&&!this.tabReleased&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault(),e.shiftKey?this.outdent():this.indent();return}if(e.key!=="Tab"&&(this.tabReleased=!1),e.key==="Enter"&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey&&!e.isComposing){let{value:r,selectionStart:i}=this.textarea,s=r.lastIndexOf(`
`,i-1)+1,l=/^[ \t]*/.exec(r.slice(s,i))?.[0]??"";l&&(e.preventDefault(),this.insert(`
${l}`))}}indent(){let{value:e,selectionStart:n,selectionEnd:a}=this.textarea;if(n===a||!e.slice(n,a).includes(`
`)){this.insert(Dn);return}let r=e.lastIndexOf(`
`,n-1)+1,i=e.slice(r,a),s=i.replace(/^/gm,Dn);this.replaceRange(r,a,s),this.textarea.setSelectionRange(n+Dn.length,a+(s.length-i.length))}outdent(){let{value:e,selectionStart:n,selectionEnd:a}=this.textarea,r=e.lastIndexOf(`
`,n-1)+1,i=e.slice(r,a),s=new RegExp(`^(?:\\t| {1,${Dn.length}})`,"gm"),l=(/^(?:\t| {1,2})/.exec(i)?.[0]??"").length,c=i.replace(s,"");c!==i&&(this.replaceRange(r,a,c),this.textarea.setSelectionRange(Math.max(r,n-l),a-(i.length-c.length)))}insert(e){this.textarea.focus(),document.execCommand?.("insertText",!1,e)||(this.textarea.setRangeText(e,this.textarea.selectionStart,this.textarea.selectionEnd,"end"),this.onInput("insertText"))}replaceRange(e,n,a){this.textarea.setSelectionRange(e,n),this.insert(a)}undo(){this.restore(this.history.undo())}redo(){this.restore(this.history.redo())}restore(e){e&&(this.textarea.value=e.value,this.textarea.focus(),this.textarea.setSelectionRange(e.start,e.end),this.text=e.value,this.changedSinceFocus=!0,this.refresh(),this.options.onInput(this.text))}destroy(){clearTimeout(this.timer)}};var Oi=Object.freeze({mapRole:"map",mapSummary:"World map, {projection} projection: {places} places, {countries} countries highlighted, {routes} routes.",mapKeyboardHelp:"Drag or use the arrow keys to move, the wheel or + and - to zoom, 0 to reset. The list under the map gives every item.",mapProjection:"Projection","mapProjection_natural-earth":"Natural Earth","mapProjection_equal-earth":"Equal Earth",mapProjection_mercator:"Mercator",mapProjection_equirectangular:"Equirectangular",mapProjection_globe:"Globe (3D)","mapProjection_azimuthal-equal-area":"Azimuthal equal-area","mapProjection_azimuthal-equidistant":"Azimuthal equidistant",mapProjection_stereographic:"Stereographic",mapProjection_gnomonic:"Gnomonic","mapProjection_transverse-mercator":"Transverse Mercator","mapProjection_conic-equal-area":"Conic equal-area","mapProjection_conic-conformal":"Conic conformal",mapBasemap:"Map style",mapBasemap_light:"Light",mapBasemap_dark:"Dark",mapBasemap_political:"Political",mapBasemap_satellite:"Seen from the sky",mapBasemap_night:"Night",mapBasemap_blueprint:"Blueprint",mapBasemap_vintage:"Vintage",mapBasemap_mono:"Monochrome",mapGraticule:"Grid",mapSearch:"Find a place",mapSearchPlaceholder:"Coordinates, city, country or address",mapZoomIn:"Zoom in",mapZoomOut:"Zoom out",mapReset:"Reset the view",mapPlaces:"{count} places",mapCopyPlaces:"Copy the places",mapLegend:"Color scale",mapList:"Places, countries and routes",mapKind_marker:"Place",mapKind_country:"Country",mapKind_route:"Route",mapKind_shape:"Shape",mapKind_pin:"Pin",mapShow:"Show {label} on the map",mapShape:"Shape",mapDistance:"{km} km",mapLocating:"Locating\u2026",mapNeedsGeocoder:"Address: needs a geocoder",mapNoGeocoder:"\u201C{query}\u201D is an address: this map has no geocoder (geocoder attribute).",mapGeocoding:"Looking for \u201C{query}\u201D\u2026",mapNotFound:"Nothing found for \u201C{query}\u201D.",mapFound:"{label}: {coords}",mapFoundCountry:"{name}",mapSelectedPoint:"{label} selected, {coords}",mapSelectedCountry:"{name} selected",mapInvalidLines:"Lines not understood: {list}",mapLoadFailed:"The map could not be loaded: {message}",mapTrack:"Track the target",mapTracking:"Tracking {label}\u2026",mapTargetLocated:"Target located: {label}, {coords}",mapStop:"Stop"}),Ii={mapRole:"carte",mapSummary:"Carte du monde, projection {projection} : {places} lieux, {countries} pays mis en avant, {routes} trajets.",mapKeyboardHelp:"Glissez ou utilisez les fl\xE8ches pour vous d\xE9placer, la molette ou + et - pour zoomer, 0 pour revenir au d\xE9part. La liste sous la carte donne chaque \xE9l\xE9ment.",mapProjection:"Projection",mapProjection_globe:"Globe (3D)",mapProjection_equirectangular:"\xC9quirectangulaire","mapProjection_azimuthal-equal-area":"Azimutale \xE9quivalente","mapProjection_azimuthal-equidistant":"Azimutale \xE9quidistante",mapProjection_stereographic:"St\xE9r\xE9ographique",mapProjection_gnomonic:"Gnomonique","mapProjection_transverse-mercator":"Mercator transverse","mapProjection_conic-equal-area":"Conique \xE9quivalente","mapProjection_conic-conformal":"Conique conforme",mapBasemap:"Style",mapBasemap_light:"Clair",mapBasemap_dark:"Sombre",mapBasemap_political:"Politique",mapBasemap_satellite:"Vue du ciel",mapBasemap_night:"Nuit",mapBasemap_blueprint:"Plan",mapBasemap_vintage:"Ancien",mapBasemap_mono:"Monochrome",mapGraticule:"Grille",mapSearch:"Trouver un lieu",mapSearchPlaceholder:"Coordonn\xE9es, ville, pays ou adresse",mapZoomIn:"Zoomer",mapZoomOut:"D\xE9zoomer",mapReset:"Revenir \xE0 la vue de d\xE9part",mapPlaces:"{count} lieux",mapCopyPlaces:"Copier les lieux",mapLegend:"\xC9chelle de couleurs",mapList:"Lieux, pays et trajets",mapKind_marker:"Lieu",mapKind_country:"Pays",mapKind_route:"Trajet",mapKind_shape:"Forme",mapKind_pin:"Rep\xE8re",mapShow:"Montrer {label} sur la carte",mapShape:"Forme",mapDistance:"{km} km",mapLocating:"Recherche\u2026",mapNeedsGeocoder:"Adresse : il faut un g\xE9ocodeur",mapNoGeocoder:"\xAB {query} \xBB est une adresse : cette carte n\u2019a pas de g\xE9ocodeur (attribut geocoder).",mapGeocoding:"Recherche de \xAB {query} \xBB\u2026",mapNotFound:"Rien trouv\xE9 pour \xAB {query} \xBB.",mapSelectedPoint:"{label} s\xE9lectionn\xE9, {coords}",mapSelectedCountry:"{name} s\xE9lectionn\xE9",mapInvalidLines:"Lignes non comprises : {list}",mapLoadFailed:"La carte n\u2019a pas pu \xEAtre charg\xE9e : {message}",mapTrack:"Traquer la cible",mapTracking:"Traque de {label}\u2026",mapTargetLocated:"Cible localis\xE9e : {label}, {coords}",mapStop:"Arr\xEAter"};var su="004AFAFG 008ALALB 010AQATA 012DZDZA 024AOAGO 031AZAZE 032ARARG 036AUAUS 040ATAUT 044BSBHS 050BDBGD 051AMARM 056BEBEL 064BTBTN 068BOBOL 070BABIH 072BWBWA 076BRBRA 084BZBLZ 090SBSLB 096BNBRN 100BGBGR 104MMMMR 108BIBDI 112BYBLR 116KHKHM 120CMCMR 124CACAN 140CFCAF 144LKLKA 148TDTCD 152CLCHL 156CNCHN 158TWTWN 170COCOL 178CGCOG 180CDCOD 188CRCRI 191HRHRV 192CUCUB 196CYCYP 203CZCZE 204BJBEN 208DKDNK 214DODOM 218ECECU 222SVSLV 226GQGNQ 231ETETH 232ERERI 233EEEST 238FKFLK 242FJFJI 246FIFIN 250FRFRA 260TFATF 262DJDJI 266GAGAB 268GEGEO 270GMGMB 275PSPSE 276DEDEU 288GHGHA 300GRGRC 304GLGRL 320GTGTM 324GNGIN 328GYGUY 332HTHTI 340HNHND 348HUHUN 352ISISL 356ININD 360IDIDN 364IRIRN 368IQIRQ 372IEIRL 376ILISR 380ITITA 384CICIV 388JMJAM 392JPJPN 398KZKAZ 400JOJOR 404KEKEN 408KPPRK 410KRKOR 414KWKWT 417KGKGZ 418LALAO 422LBLBN 426LSLSO 428LVLVA 430LRLBR 434LYLBY 440LTLTU 442LULUX 450MGMDG 454MWMWI 458MYMYS 466MLMLI 478MRMRT 484MXMEX 496MNMNG 498MDMDA 499MEMNE 504MAMAR 508MZMOZ 512OMOMN 516NANAM 524NPNPL 528NLNLD 540NCNCL 548VUVUT 554NZNZL 558NINIC 562NENER 566NGNGA 578NONOR 586PKPAK 591PAPAN 598PGPNG 600PYPRY 604PEPER 608PHPHL 616PLPOL 620PTPRT 624GWGNB 626TLTLS 630PRPRI 634QAQAT 642ROROU 643RURUS 646RWRWA 682SASAU 686SNSEN 688RSSRB 694SLSLE 703SKSVK 704VNVNM 705SISVN 706SOSOM 710ZAZAF 716ZWZWE 724ESESP 728SSSSD 729SDSDN 732EHESH 740SRSUR 748SZSWZ 752SESWE 756CHCHE 760SYSYR 762TJTJK 764THTHA 768TGTGO 780TTTTO 784AEARE 788TNTUN 792TRTUR 795TMTKM 800UGUGA 804UAUKR 807MKMKD 818EGEGY 826GBGBR 834TZTZA 840USUSA 854BFBFA 858UYURY 860UZUZB 862VEVEN 887YEYEM 894ZMZMB",Bi=Object.freeze({Kosovo:["XK","XKX"],"N. Cyprus":["","CYN"],Somaliland:["","SOL"]}),Qt=new Map,Ve=new Map;for(let t of su.split(" ")){let e={numeric:t.slice(0,3),a2:t.slice(3,5),a3:t.slice(5,8)};Qt.set(e.numeric,e),Ve.set(e.a2,e),Ve.set(e.a3,e)}for(let[t,[e,n]]of Object.entries(Bi)){let a={numeric:t,a2:e,a3:n};Qt.set(t,a),e&&Ve.set(e,a),Ve.set(n,a)}var iu=Object.freeze({usa:"US","united states of america":"US",america:"US","etats-unis":"US","etats unis":"US",uk:"GB","great britain":"GB",britain:"GB",england:"GB",scotland:"GB",wales:"GB",angleterre:"GB","grande-bretagne":"GB","royaume uni":"GB",holland:"NL","czech republic":"CZ","republique tcheque":"CZ","ivory coast":"CI","cote divoire":"CI",drc:"CD","dr congo":"CD","congo-kinshasa":"CD","congo kinshasa":"CD","congo-brazzaville":"CG",burma:"MM",swaziland:"SZ",eswatini:"SZ",macedonia:"MK","north macedonia":"MK","south korea":"KR","north korea":"KP","coree du sud":"KR","coree du nord":"KP",russia:"RU","russian federation":"RU","east timor":"TL","cape verde":"CV",vatican:"VA",persia:"IR","western sahara":"EH","w. sahara":"EH",bosnia:"BA","bosnia and herzegovina":"BA",turkiye:"TR","the netherlands":"NL","the bahamas":"BS"});function mt(t){return t.normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/[’'`.]/g,"").replace(/[\s_]+/g," ").trim()}var Di=new Map;function Pi(t){let e=t.split("-")[0]||"en",n=Di.get(e);if(n)return n;let a=new Map(Object.entries(iu));for(let r of new Set(["en","fr",e])){let i=zi(r);if(i)for(let{a2:s}of Ve.values()){if(!s)continue;let l=i.of(s);l&&l!==s&&a.set(mt(l),s)}}return Di.set(e,a),a}var Pn=new Map;function zi(t){if(!Pn.has(t))try{Pn.set(t,new Intl.DisplayNames([t],{type:"region"}))}catch{Pn.set(t,null)}return Pn.get(t)??null}function Bn(t,e=""){return Qt.get(t??e)??Qt.get(e)??{numeric:t??e,a2:"",a3:""}}function qe(t,e="en"){let n=t.trim();if(!n)return null;if(/^[A-Za-z]{2,3}$/.test(n)&&Ve.has(n.toUpperCase())&&(n===n.toUpperCase()||!Pi(e).has(mt(n))))return Ve.get(n.toUpperCase())??null;if(/^\d{3}$/.test(n))return Qt.get(n)??null;let a=mt(n),r=Pi(e).get(a);if(r)return Ve.get(r)??null;for(let[i,s]of Object.entries(Bi))if(mt(i)===a)return Ve.get(s[1])??null;return null}function Le(t,e,n=""){if(!t.a2)return n||t.a3;let a=zi(e)?.of(t.a2);return a&&a!==t.a2?a:n||t.a2}function Ga(t){return/^[A-Z]{2}$/.test(t)?String.fromCodePoint(...[...t].map(e=>127462+e.charCodeAt(0)-65)):""}var ou=`Paris|FR|48.8566|2.3522
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
South Pole,P\xF4le Sud|AQ|-90|0`,en=null;function Ui(t){if(!en){en=new Map;for(let n of ou.split(`
`)){let[a,r,i,s]=n.split("|"),l=a.split(","),c={name:l[0],country:r,lat:Number(i),lon:Number(s)};for(let d of l)en.set(mt(d),c)}}let e=mt(t);return en.get(e)??en.get(e.replace(/,.*$/,"").trim())??null}var Va=2e3,qa=/^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i,ji=/\s*(?:->|→|=>|⟶)\s*/;function Ka(t,e="en"){let n=t.trim();if(/^[[{]/.test(n))try{return cu(JSON.parse(n),e)}catch{}let a=[],r=[];for(let i of n.split(/\r?\n/)){let s=i.trim();if(!s||s.startsWith("//")||s.startsWith("; "))continue;if(a.length>=Va)break;let l=lu(s,e);l?a.push(l):r.push(s)}return{items:a,invalid:r,view:{}}}function lu(t,e="en"){let n=t,a="",r=n.match(/\s+(#[0-9a-f]{3,8})$/i)??n.match(/^(#[0-9a-f]{3,8})\s+/i);r&&qa.test(r[1])&&(a=r[1],n=n.replace(r[0]," ").trim());let i="",s=n.match(/^([^:]{1,80}?)\s*:\s+(.+)$/);if(s&&!/^(?:geo|https?)$/i.test(s[1])&&(i=s[1].trim(),n=s[2].trim()),ji.test(n)){let x=n.split(ji).filter(Boolean).map(b=>tt(b,e));return x.length<2||x.some(b=>!b)?null:{kind:"route",label:i,color:a,stops:x,text:t}}let l=n.match(/^(.+?)\s*(?:=\s*)?([+-]?\d+(?:[.,]\d+)?)\s*(%)?$/),c=qe(n,e)??(l?qe(l[1],e):null);if(c&&!tn(n)){let x=c===qe(n,e)||!l?null:Number(l[2].replace(",","."));return{kind:"country",code:c,label:i,color:a,value:x,text:t}}let d=n.match(/^([+-]?\d{1,3}(?:\.\d+)?)\s*[,; ]\s*([+-]?\d{1,3}(?:\.\d+)?)\s+([^\d\s°'"′″].*)$/u);if(d&&!i){let x=tn(`${d[1]}, ${d[2]}`);if(x)return Pt(d[3].trim(),a,{...x,source:"coords"},t)}if(!i&&!tn(n)){let x=n.split(/\s+/);for(let b=x.length-1;b>=2;b--){let w=tn(x.slice(0,b).join(" "));if(w)return Pt(x.slice(b).join(" "),a,{...w,source:"coords"},t)}}let p=tt(n,e);return p?Pt(i,a,p,t):null}function Pt(t,e,n,a){return{kind:"marker",label:t,color:e,place:n,text:a}}function tt(t,e="en"){let n=t.trim();if(!n)return null;let a=tn(n);if(a)return{...a,source:"coords"};let r=Ui(n);if(r)return{lat:r.lat,lon:r.lon,source:"city",name:r.name};let i=qe(n,e);return i?{country:i}:/\p{L}/u.test(n)&&n.length<=300?{address:n}:null}function tn(t){let e=t.trim();if(!e||e.length>200)return null;let n=e.match(/^geo:([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)/i)??e.match(/@([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)/)??e.match(/[?&](?:q|ll|query)=([+-]?\d+(?:\.\d+)?)(?:,|%2C)\s*([+-]?\d+(?:\.\d+)?)/i)??e.match(/[#&]map=\d+(?:\.\d+)?\/([+-]?\d+(?:\.\d+)?)\/([+-]?\d+(?:\.\d+)?)/);if(n)return gt(Number(n[1]),Number(n[2]));let a=e.match(/[?&]mlat=([+-]?\d+(?:\.\d+)?)/),r=e.match(/[?&]mlon=([+-]?\d+(?:\.\d+)?)/);if(a&&r)return gt(Number(a[1]),Number(r[1]));if(!/^[\s\d.,;:+\-°º'′’"″NSEWOnsewo]+$/.test(e)||!/\d/.test(e)||/[a-z]{2}/i.test(e))return null;let i=[],s={},l="",c=e.match(/[NSEWO]|[+-]?\d+(?:\.\d+)?\s*(?:°|º|''|["″]|['′’])?/gi)??[];for(let b of c){let w=b.trim();if(/^[NSEWO]$/i.test(w)){let N=w.toUpperCase()==="O"?"W":w.toUpperCase();s.deg!==void 0&&!s.hem&&!l?s.hem=N:(s.deg!==void 0&&i.push(s),s={},l=N);continue}let h=Number.parseFloat(w),y=w.replace(/^[+-]?\d+(?:\.\d+)?\s*/,"");/^(?:''|["″])$/.test(y)?s.sec=h:/^['′’]$/.test(y)?s.min=h:(s.deg!==void 0&&(i.push(s),s={}),s.deg=Math.abs(h),s.negative=h<0||Object.is(h,-0)||w.startsWith("-"),l&&(s.hem=l,l=""))}if(s.deg!==void 0&&i.push(s),i.length!==2)return null;let d=b=>{if((b.min??0)>=60||(b.sec??0)>=60)return NaN;let w=(b.deg??0)+(b.min??0)/60+(b.sec??0)/3600;return b.negative||b.hem==="S"||b.hem==="W"?-w:w},[p,x]=i;return(p.hem==="E"||p.hem==="W")&&(!x.hem||x.hem==="N"||x.hem==="S")&&([p,x]=[x,p]),p.hem==="E"||p.hem==="W"||x.hem==="N"||x.hem==="S"?null:gt(d(p),d(x))}function gt(t,e){return!Number.isFinite(t)||!Number.isFinite(e)||Math.abs(t)>90||Math.abs(e)>180?null:{lat:t,lon:e}}function cu(t,e="en"){let n=[],a=[],r={},i=h=>typeof h=="string"||typeof h=="number"?String(h):"",s=h=>{let y=i(h?.color??h?.["marker-color"]??h?.stroke??h?.fill);return qa.test(y)?y:""},l=h=>i(h?.label??h?.name??h?.title??h?.text).slice(0,200),c=h=>{if(typeof h=="string")return tt(h,e);if(Array.isArray(h)&&h.length>=2)return Fi(gt(Number(h[1]),Number(h[0])));if(!h||typeof h!="object")return null;let y=h.lat??h.latitude,N=h.lon??h.lng??h.long??h.longitude;if(y!==void 0&&N!==void 0)return Fi(gt(Number(y),Number(N)));let I=i(h.address??h.place??h.city??h.query??h.coords);return I?tt(I,e):null},d=h=>{let y=h?.type==="Feature"?h.geometry:h,N=h?.type==="Feature"?h.properties??{}:{};if(!y||typeof y.type!="string")return;let I=l(N),P=s(N);if(y.type==="Point"){let H=c(y.coordinates);H?n.push(Pt(I,P,H,I)):a.push(JSON.stringify(y.coordinates))}else if(y.type==="MultiPoint")for(let H of y.coordinates??[]){let B=c(H);B&&n.push(Pt(I,P,B,I))}else if(y.type==="GeometryCollection")for(let H of y.geometries??[])d({type:"Feature",properties:N,geometry:H});else/^(?:Multi)?(?:LineString|Polygon)$/.test(y.type)&&n.push({kind:"shape",label:I,color:P,geometry:y,text:I||y.type})};if(t?.type==="FeatureCollection"){for(let h of(t.features??[]).slice(0,Va))d(h);return{items:n,invalid:a,view:r}}if(t?.type==="Feature"||/^(?:Multi)?(?:Point|LineString|Polygon)$|^GeometryCollection$/.test(t?.type??""))return d(t),{items:n,invalid:a,view:r};let p=Array.isArray(t)?t:t?.markers??t?.places??t?.points??[];for(let h of Array.isArray(p)?p.slice(0,Va):[]){let y=c(h);y&&!("country"in y)?n.push(Pt(l(h),s(h),y,l(h)||JSON.stringify(h))):a.push(typeof h=="string"?h:JSON.stringify(h))}let x=t?.countries??t?.highlight,b=Array.isArray(x)?x.map(h=>typeof h=="string"?[h,null]:[i(h?.code??h?.id??h?.country??h?.name),h]):x&&typeof x=="object"?Object.entries(x):[];for(let[h,y]of b){let N=qe(h,e);if(!N){a.push(h);continue}let I=typeof y=="number"?y:typeof y?.value=="number"?y.value:null,P=typeof y=="string"&&qa.test(y)?y:s(y);n.push({kind:"country",code:N,label:l(y),color:P,value:I,text:h})}for(let h of Array.isArray(t?.routes)?t.routes:[]){let y=Array.isArray(h)?h:h?.stops??[h?.from,h?.to],N=(Array.isArray(y)?y:[]).map(c);N.length>=2&&N.every(Boolean)?n.push({kind:"route",label:l(h),color:s(h),stops:N,text:l(h)||"route"}):a.push(JSON.stringify(h))}for(let h of Array.isArray(t?.features)?t.features:[])d(h);let w=t?.center?c(t.center):null;return w&&"lat"in w&&(r.center={lat:w.lat,lon:w.lon}),typeof t?.zoom=="number"&&(r.zoom=t.zoom),{items:n,invalid:a,view:r}}function Fi(t){return t?{...t,source:"coords"}:null}function ge(t,e,n="decimal"){if(n==="decimal")return`${t.toFixed(5)}, ${e.toFixed(5)}`;let a=(r,i,s)=>{let l=Math.abs(r),c=Math.floor(l),d=Math.floor((l-c)*60),p=Math.round(((l-c)*60-d)*600)/10;return p>=60&&([p,d]=[0,d+1]),d>=60&&([d,c]=[0,c+1]),`${c}\xB0${String(d).padStart(2,"0")}\u2032${p.toFixed(1).padStart(4,"0")}\u2033${r<0?s:i}`};return`${a(t,"N","S")} ${a(e,"E","W")}`}function $i(t,e){let n=Math.PI/180,a=(e.lat-t.lat)*n,r=(e.lon-t.lon)*n,i=Math.sin(a/2)**2+Math.cos(t.lat*n)*Math.cos(e.lat*n)*Math.sin(r/2)**2;return 2*6371.0088*Math.asin(Math.min(1,Math.sqrt(i)))}function Hi(t){let e=Array.isArray(t)?t[0]:t?.features?.[0]??t?.results?.[0]??t;if(!e||typeof e!="object")return null;let n=String(e.display_name??e.properties?.label??e.properties?.display_name??e.properties?.name??e.formatted_address??e.name??""),a=e.geometry?.coordinates;if(Array.isArray(a)){let s=gt(Number(a[1]),Number(a[0]));return s?{...s,name:n}:null}let r=e.geometry?.location??e,i=gt(Number(r.lat??r.latitude),Number(r.lon??r.lng??r.longitude));return i?{...i,name:n}:null}function Gi(t,e,n="en"){let a=encodeURIComponent(e),i={nominatim:`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&accept-language=${encodeURIComponent(n)}&q={q}`,photon:"https://photon.komoot.io/api/?limit=1&q={q}",ban:"https://api-adresse.data.gouv.fr/search/?limit=1&q={q}"}[t.trim().toLowerCase()]??t.trim();return!/^https?:\/\//i.test(i)||!i.includes("{q}")?null:i.replaceAll("{q}",a)}var zn=null;function Wa(){if(zn)return zn;let t=J().vendorUrl||os(),e={ready:!1,geo:null,promise:Promise.resolve()};return e.promise=import(new URL("geo.js",t||location.href).href).then(n=>(e.geo=n,e.ready=!0,n),n=>{throw zn=null,n}),zn=e,e}bn({en:Oi,fr:Ii});var uu="http://www.w3.org/2000/svg",Fe=960,we=540,Ya=60,du=25,Vi=["natural-earth","equal-earth","mercator","equirectangular","globe","azimuthal-equal-area","azimuthal-equidistant","stereographic","gnomonic","transverse-mercator","conic-equal-area","conic-conformal"],Ke=new Set(["globe","azimuthal-equal-area","azimuthal-equidistant","stereographic","gnomonic"]),Za={globe:90,stereographic:120,gnomonic:60,"azimuthal-equal-area":179.9,"azimuthal-equidistant":179.9},qi=["light","dark","political","satellite","night","blueprint","vintage","mono"],Ki=new WeakMap,nn=new Map;function $(t,e={}){let n=document.createElementNS(uu,t);for(let[a,r]of Object.entries(e))r!==null&&n.setAttribute(a,String(r));return n}var Ja=class extends Je{static type="map";static componentAttributes=Object.freeze(["projection","basemap","center","zoom","highlight","geocoder","graticule","labels","controls","list","pick","scroll-zoom","coords-format","height","movie"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,download:!0,fullscreen:!0,controls:!0,list:!0}};static styles=[Nr];static allowEmpty=!0;static upgradeProperties=["content"];constructor(){super(),this.viewState=null,this.projectionState=null,this.basemapState=null,this.graticuleState=null,this.selected=null,this.pins=[],this.projection=null,this.path=null,this.svgEl=null,this.stage=null,this.tooltip=null,this.readout=null,this.statusLine=null,this.countryEls=[],this.updaters=[],this.frameRequest=0,this.flight=0,this.editor=null,this.previewTimer=void 0,this.geocoding=null,this.movie=null,this.changeTimer=void 0}disconnectedCallback(){cancelAnimationFrame(this.frameRequest),cancelAnimationFrame(this.flight),this.movie?.abort(),clearTimeout(this.previewTimer),clearTimeout(this.changeTimer),this.geocoding?.abort(),this.editor?.destroy(),super.disconnectedCallback()}flag(e,n){return Ie(this.getAttribute(e))??n}input(){let e=Ka(this.text??"",this.locale);for(let n of(this.getAttribute("highlight")??"").split(/[\s,;]+/).filter(Boolean)){let a=qe(n,this.locale);a&&!e.items.some(r=>r.kind==="country"&&r.code.a3===a.a3)&&e.items.push({kind:"country",code:a,label:"",color:"",value:null,text:n})}return e}get projectionName(){let e=(this.projectionState??this.getAttribute("projection")??"").toLowerCase(),a={orthographic:"globe","3d":"globe",flat:"natural-earth","plate-carree":"equirectangular",azimuthal:"azimuthal-equidistant"}[e]??e;return Vi.includes(a)?a:"natural-earth"}get basemap(){let e=(this.basemapState??this.getAttribute("basemap")??"").toLowerCase(),a={sky:"satellite",terrain:"satellite",earth:"satellite",space:"night"}[e]??e;return qi.includes(a)?a:"light"}initialView(){let e=Ka(this.text??"",this.locale).view,n=this.getAttribute("center"),a=n?tt(n,this.locale):null,r=e.center??null;a&&"lat"in a?r=a:a&&"country"in a&&(r=this.countryCenter(a.country));let i=Number(this.getAttribute("zoom")??e.zoom??1);return{lon:r?.lon??(this.projectionName==="globe"?10:0),lat:r?.lat??(Ke.has(this.projectionName)?30:0),zoom:Number.isFinite(i)?Math.min(Ya,Math.max(1,i)):1}}get view(){let e=this.viewState??this.initialView();return{lat:e.lat,lon:e.lon,zoom:e.zoom,projection:this.projectionName,basemap:this.basemap}}get items(){return this.input().items.map(e=>{if(e.kind==="country")return{kind:"country",label:e.label||Le(e.code,this.locale),code:e.code.a2||e.code.a3,value:e.value};if(e.kind==="marker"){let n=this.locate(e.place);return{kind:"marker",label:this.markerLabel(e),lat:n?.lat,lon:n?.lon}}return{kind:e.kind,label:e.label}})}locate(e){if("lat"in e)return e;if("country"in e)return this.countryCenter(e.country);let n=nn.get(e.address.toLowerCase());return n&&n!=="none"&&n!=="pending"?n:null}markerLabel(e){let n=e.place;return e.label?e.label:"name"in n&&n.name?n.name:"address"in n?n.address:"country"in n?Le(n.country,this.locale):ge(n.lat,n.lon,this.coordsFormat)}get coordsFormat(){return this.getAttribute("coords-format")==="dms"?"dms":"decimal"}renderContent(e){let n=this.t,{items:a,invalid:r}=this.input(),i=g("div",{class:"body map-body",part:"body"});this.feature("controls")&&i.append(this.controlsView()),this.stage=g("div",{class:"map-stage",part:"stage",attrs:{"data-basemap":this.basemap}});let s=this.getAttribute("height");s&&/^[\d.]+(?:px|em|rem|vh|%)$/.test(s)&&(this.stage.style.height=s),i.append(this.stage),this.statusLine=g("p",{class:"map-status",attrs:{role:"status"}}),i.append(this.statusLine);let l=g("div",{class:"map-legend-host"});i.append(l),this.feature("list")&&i.append(g("div",{class:"map-list-host"})),r.length&&i.append(g("p",{class:"map-muted",text:n("mapInvalidLines",{list:r.slice(0,5).join(" \xB7 ")})}));let c=g("div",{class:"panel"}),d=[];if(this.editing){let w=this.createEditor();c.classList.add("map-edit"),c.append(g("div",{class:"body editor-body",part:"body editor"},w.element),i),d=this.historyButtons(w)}else c.append(i);let p=[...d,this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.geoJson(),this.downloadName("map.geojson"),"application/geo+json"):null,this.feature("copy")?this.copyButton(()=>this.report(),n("mapCopyPlaces")):null],x=a.filter(w=>w.kind==="marker").length,b=x?`${n(`mapProjection_${this.projectionName}`)} \xB7 ${n("mapPlaces",{count:x})}`:n(`mapProjection_${this.projectionName}`);e.append(...this.chrome({badge:b,actions:p}),c),this.editor?.align(),this.draw()}controlsView(){let e=this.t,n=(s,l,c,d,p,x)=>{let b=Ne(s),w=g("select",{class:"map-select",attrs:{id:b,"data-focus-key":s},on:{change:()=>x(w.value)}},...l.map(h=>g("option",{text:p(h),attrs:{value:h,selected:h===c}})));return g("div",{class:"map-control"},g("label",{attrs:{for:b},text:e(d)}),w)},a=Ne("place"),r=g("input",{class:"map-search-input",attrs:{id:a,type:"search",autocomplete:"off",spellcheck:"false",placeholder:e("mapSearchPlaceholder"),"data-focus-key":"place"}}),i=g("form",{class:"map-search",attrs:{role:"search"},on:{submit:s=>{s.preventDefault(),this.find(r.value)}}},g("label",{class:"sr-only",attrs:{for:a},text:e("mapSearch")}),r,g("button",{class:"btn map-go",attrs:{type:"submit","aria-label":e("mapSearch"),title:e("mapSearch")}},Ue("search")));return g("div",{class:"map-controls",part:"controls"},i,n("projection",Vi,this.projectionName,"mapProjection",s=>e(`mapProjection_${s}`),s=>{let l=Ke.has(this.projectionName);this.projectionState=s,this.viewState&&l!==Ke.has(s)&&(this.viewState.zoom=1),this.redrawAll(),this.changed()}),n("basemap",qi,this.basemap,"mapBasemap",s=>e(`mapBasemap_${s}`),s=>{this.basemapState=s,this.redrawAll(),this.changed()}),g("label",{class:"map-check"},g("input",{attrs:{type:"checkbox",checked:this.showGraticule,"data-focus-key":"graticule"},on:{change:s=>{this.graticuleState=s.target.checked,this.redrawAll()}}}),g("span",{text:e("mapGraticule")})))}get showGraticule(){return this.graticuleState??this.flag("graticule",!0)}redrawAll(){if(!this.stage)return;this.stage.dataset.basemap=this.basemap,this.draw();let e=this.root.querySelector(".badge");e&&(e.textContent=e.textContent?.replace(/^[^·]+/,`${this.t(`mapProjection_${this.projectionName}`)} `).trim()??"")}draw(){let e=this.stage;if(!e)return;let n=Wa();if(!n.ready){e.replaceChildren(_n(this.t)),n.promise.then(()=>{this.stage===e&&(this.draw(),this.renderSide())},a=>{this.stage===e&&e.replaceChildren(Rt(this.t("mapLoadFailed",{message:String(a?.message??a)})))});return}this.build(n.geo),this.renderSide(),this.geocodeItems()}get geo(){return Wa().geo}build(e){let n=this.t,a=this.stage,{items:r}=this.input(),i=this.projectionName,s={glow:Ne("glow"),shade:Ne("shade"),clip:Ne("clip"),ocean:Ne("ocean")};this.updaters=[],this.countryEls=[];let l=$("svg",{viewBox:`0 0 ${Fe} ${we}`,class:"map-svg",part:"map",role:"application","aria-roledescription":n("mapRole"),tabindex:"0",preserveAspectRatio:"xMidYMid meet"});l.setAttribute("aria-label",this.summary(r));let c=Ne("help");l.setAttribute("aria-describedby",c),this.svgEl=l;let d=$("defs"),p=$("radialGradient",{id:s.ocean,cx:"50%",cy:"45%",r:"60%"});p.append($("stop",{offset:"0%",class:"ocean-a"}),$("stop",{offset:"100%",class:"ocean-b"}));let x=$("radialGradient",{id:s.shade,cx:"35%",cy:"30%",r:"75%"});x.append($("stop",{offset:"0%",class:"shade-a"}),$("stop",{offset:"65%",class:"shade-b"}),$("stop",{offset:"100%",class:"shade-c"}));let b=$("filter",{id:s.glow,x:"-20%",y:"-20%",width:"140%",height:"140%"});b.append($("feGaussianBlur",{stdDeviation:"12"}));let w=$("clipPath",{id:s.clip}),h=$("path");w.append(h),d.append(p,x,b,w),l.append(d);let y=Ke.has(i);if(y&&(this.basemap==="night"||this.basemap==="satellite")){let E=$("g",{class:"map-stars","aria-hidden":"true"}),L=7,D=()=>(L=L*16807%2147483647)/2147483647;for(let W=0;W<140;W++)E.append($("circle",{cx:(D()*Fe).toFixed(1),cy:(D()*we).toFixed(1),r:(D()*1.2+.2).toFixed(2),opacity:(D()*.7+.3).toFixed(2)}));l.append(E)}let N=$("path",{class:"map-atmosphere",filter:`url(#${s.glow})`}),I=$("path",{class:"map-sphere",fill:`url(#${s.ocean})`}),P=$("path",{class:"map-graticule"}),H=$("g",{class:"map-countries","clip-path":`url(#${s.clip})`}),B=$("path",{class:"map-borders"}),q=$("g",{class:"map-overlay","clip-path":`url(#${s.clip})`}),X=$("path",{class:"map-shading",fill:`url(#${s.shade})`}),ne=$("g",{class:"map-pins"}),re=$("g",{class:"map-labels","aria-hidden":"true"});y&&l.append(N),l.append(I),this.showGraticule&&l.append(P),l.append(H,B,q),i==="globe"&&l.append(X),l.append(ne,re);let Re=new Map(r.filter(E=>E.kind==="country").map(E=>[E.code.a3,E])),Se=[...Re.values()].map(E=>E.value).filter(E=>E!==null),ae=Math.min(...Se),ye=Math.max(...Se);for(let[E,L]of e.countries.entries()){let D=Bn(L.id,L.properties?.name),W=Le(D,this.locale,L.properties?.name),z=Re.get(D.a3),Q=$("path",{class:`map-country c${E%8}${this.basemap==="satellite"?` ${pu(e,L,D)}`:""}`,"data-code":D.a2||D.a3});if(z){if(Q.classList.add("highlighted"),z.color)Q.style.setProperty("fill",z.color);else if(z.value!==null&&Se.length){let K=ye===ae?100:Math.round((z.value-ae)/(ye-ae)*100);Q.style.setProperty("fill",`color-mix(in oklab, var(--map-high) ${K}%, var(--map-low))`)}}this.selected===D.a3&&Q.classList.add("selected"),H.append(Q),this.countryEls.push({el:Q,feature:L,code:D,name:W})}let Pe=this.flag("labels",!0),ke=E=>!y||e.geoDistance?.([E.lon,E.lat],[-this.projection.rotate()[0],-this.projection.rotate()[1]])<(Za[i]??90)*Math.PI/180;for(let E of r){if(E.kind==="shape"){let L=$("path",{class:`map-shape ${/Polygon/.test(E.geometry.type)?"area":"line"}`});E.color&&L.style.setProperty("--map-item",E.color),L.append(this.titleEl(E.label||n("mapShape"))),q.append(L),this.updaters.push(()=>L.setAttribute("d",this.path(E.geometry)??""))}if(E.kind==="route"){let L=$("path",{class:"map-route"});E.color&&L.style.setProperty("--map-item",E.color),q.append(L),this.updaters.push(()=>{let D=E.stops.map(z=>this.locate(z));if(D.some(z=>!z))return L.removeAttribute("d");let W={type:"LineString",coordinates:D.map(z=>[z.lon,z.lat])};L.setAttribute("d",this.path(W)??"")})}}let Me=[...r.flatMap(E=>E.kind==="marker"?[{place:E.place,label:this.markerLabel(E),color:E.color,dropped:!1}]:[]),...this.pins.map(E=>({place:{lat:E.lat,lon:E.lon,source:"coords"},label:E.label,color:"",dropped:!0}))];for(let E of Me){let L=$("g",{class:`map-pin${E.dropped?" dropped":""}`});E.color&&L.style.setProperty("--map-item",E.color),L.append($("path",{d:"M0 0C-2-6-8-9-8-15a8 8 0 1 1 16 0c0 6-6 9-8 15Z",class:"map-pin-shape"}),$("circle",{cx:"0",cy:"-15",r:"3",class:"map-pin-dot"}),this.titleEl(E.label)),ne.append(L);let D=Pe?$("text",{class:"map-label",dx:"10",dy:"-12"}):null;D&&(D.textContent=E.label,re.append(D)),L.addEventListener("click",W=>{W.stopPropagation();let z=this.locate(E.place);z&&this.selectPoint(z,E.label)}),this.updaters.push(()=>{let W=this.locate(E.place),z=W&&ke(W)?this.projection([W.lon,W.lat]):null,Q=z&&z[0]>-20&&z[0]<Fe+20&&z[1]>-20&&z[1]<we+40;L.toggleAttribute("hidden",!Q),Q&&L.setAttribute("transform",`translate(${z[0].toFixed(1)} ${z[1].toFixed(1)})`),D&&(D.toggleAttribute("hidden",!Q),Q&&(D.setAttribute("x",z[0].toFixed(1)),D.setAttribute("y",z[1].toFixed(1))))})}if(Pe)for(let E of Re.values()){let L=this.countryCenter(E.code);if(!L)continue;let D=$("text",{class:"map-country-label","text-anchor":"middle"});D.textContent=E.label||Le(E.code,this.locale)+(E.value!==null?` \xB7 ${this.number(E.value)}`:""),re.append(D),this.updaters.push(()=>{let W=ke(L)?this.projection([L.lon,L.lat]):null;D.toggleAttribute("hidden",!W),W&&(D.setAttribute("x",W[0].toFixed(1)),D.setAttribute("y",W[1].toFixed(1)))})}this.updaters.unshift(()=>{let E=this.path({type:"Sphere"})??"";I.setAttribute("d",E),N.setAttribute("d",E),X.setAttribute("d",E),h.setAttribute("d",E),this.showGraticule&&P.setAttribute("d",this.path(e.geoGraticule10())??"");for(let L of this.countryEls)L.el.setAttribute("d",this.path(L.feature)??"");B.setAttribute("d",this.path(e.borders)??"")});let _=g("div",{class:"map-tooltip",part:"tooltip",attrs:{hidden:""}}),S=g("div",{class:"map-readout",attrs:{"aria-hidden":"true"}}),R=g("div",{class:"map-zoom"},de({icon:"plus",label:n("mapZoomIn"),key:"zoom-in",onClick:()=>this.zoomBy(2)}),de({icon:"minus",label:n("mapZoomOut"),key:"zoom-out",onClick:()=>this.zoomBy(.5)}),de({icon:"refresh",label:n("mapReset"),key:"reset",onClick:()=>this.reset()}),this.hasAttribute("movie")?this.trackButton():null),j=g("p",{class:"sr-only",attrs:{id:c},text:n("mapKeyboardHelp")});this.tooltip=_,this.readout=S,a.replaceChildren(l,R,_,S,j),a.classList.toggle("globe",y),this.bindPointer(l),this.update()}titleEl(e){let n=$("title");return n.textContent=e,n}summary(e){let n=this.t,a=r=>e.filter(i=>i.kind===r).length;return n("mapSummary",{projection:n(`mapProjection_${this.projectionName}`),places:a("marker")+this.pins.length,countries:a("country"),routes:a("route")})}update(){let e=this.geo;if(!e||!this.svgEl)return;let n=this.projectionName,a=this.viewState??this.initialView(),r=e.projections[n](),i=Ke.has(n);i?r.rotate([-a.lon,-a.lat]).clipAngle(Za[n]??90):r.rotate([-a.lon,0]),r.precision(.4);let s=12;if(n==="mercator"||n==="transverse-mercator"?r.fitExtent([[s,s],[Fe-s,we-s]],{type:"Feature",geometry:{type:"MultiPoint",coordinates:[[a.lon-179.9,-80],[a.lon+179.9,84]]}}):r.fitExtent([[s,s],[Fe-s,we-s]],{type:"Sphere"}),r.scale(r.scale()*a.zoom),i)r.translate([Fe/2,we/2]);else{r.translate([Fe/2,we/2]);let l=r([a.lon,a.lat]),c=r.translate();r.translate([c[0]+Fe/2-l[0],c[1]+we/2-l[1]]);let d=e.geoPath(r),[[,p],[,x]]=d.bounds({type:"Sphere"}),b=Number.isFinite(p)?p:-1/0,w=Number.isFinite(x)?x:1/0,h=0;w-b<=we?h=we/2-(b+w)/2:b>0?h=-b:w<we&&(h=we-w);let y=r.translate();r.translate([y[0],y[1]+h])}this.projection=r,this.path=e.geoPath(r);for(let l of this.updaters)l()}scheduleUpdate(){this.frameRequest||(this.frameRequest=requestAnimationFrame(()=>{this.frameRequest=0,this.update()}))}unitsPerPixel(){let e=this.svgEl?.getBoundingClientRect();return!e||!e.width?1:Math.max(Fe/e.width,we/e.height)}pointOf(e){let n=this.svgEl.getBoundingClientRect(),a=this.unitsPerPixel();return[Fe/2+(e.clientX-n.left-n.width/2)*a,we/2+(e.clientY-n.top-n.height/2)*a]}pan(e,n){let a=this.viewState??=this.initialView(),r=this.projection?.scale()??150,i=180/Math.PI/r;a.lon=We(a.lon-e*i);let s=Ke.has(this.projectionName)?90:85;a.lat=Math.max(-s,Math.min(s,a.lat+n*i)),this.scheduleUpdate()}zoomBy(e,n){let a=this.viewState??=this.initialView(),r=Math.min(Ya,Math.max(1,a.zoom*e));if(r!==a.zoom){if(n&&this.projection){let i=this.projection.invert?.(n);if(i&&Number.isFinite(i[0])){let s=1-a.zoom/r;a.lon=We(a.lon+We(i[0]-a.lon)*s),a.lat=a.lat+(i[1]-a.lat)*s}}a.zoom=r,this.scheduleUpdate(),this.changedSoon()}}reset(){this.viewState=null,this.selected=null,this.pins=[],this.build(this.geo),this.renderSide(),this.changed()}bindPointer(e){let n=new Map,a=0,r=0;e.addEventListener("pointerdown",s=>{s.button===0&&(e.setPointerCapture?.(s.pointerId),n.set(s.pointerId,[s.clientX,s.clientY]),a=0,n.size===2&&(r=Yi(n)))}),e.addEventListener("pointermove",s=>{this.hover(s);let l=n.get(s.pointerId);if(!l)return;let c=this.unitsPerPixel();if(n.size===2){n.set(s.pointerId,[s.clientX,s.clientY]);let x=Yi(n);r&&this.zoomBy(x/r),r=x,a+=10;return}let d=s.clientX-l[0],p=s.clientY-l[1];a+=Math.abs(d)+Math.abs(p),n.set(s.pointerId,[s.clientX,s.clientY]),a>3&&(e.classList.add("dragging"),this.pan(d*c,p*c))});let i=s=>{n.has(s.pointerId)&&(n.delete(s.pointerId),e.classList.remove("dragging"),!n.size&&a>3&&this.changed(),s.type==="pointerup"&&a<=3&&!n.size&&this.clickAt(s))};e.addEventListener("pointerup",i),e.addEventListener("pointercancel",i),e.addEventListener("pointerleave",()=>{this.tooltip&&(this.tooltip.hidden=!0),this.readout&&(this.readout.textContent="")}),e.addEventListener("dblclick",s=>{s.preventDefault(),this.zoomBy(2,this.pointOf(s))}),e.addEventListener("wheel",s=>{this.flag("scroll-zoom",!0)&&(s.preventDefault(),this.zoomBy(Math.exp(-s.deltaY*(s.deltaMode===1?.05:.0018)),this.pointOf(s)))},{passive:!1}),e.addEventListener("keydown",s=>{let d={ArrowLeft:()=>this.pan(-40,0),ArrowRight:()=>this.pan(40,0),ArrowUp:()=>this.pan(0,-40),ArrowDown:()=>this.pan(0,40),"+":()=>this.zoomBy(1.5),"=":()=>this.zoomBy(1.5),"-":()=>this.zoomBy(.6666666666666666),_:()=>this.zoomBy(.6666666666666666),0:()=>this.reset(),Home:()=>this.reset()}[s.key];!d||s.ctrlKey||s.metaKey||s.altKey||(s.preventDefault(),d(),s.key.startsWith("Arrow")&&this.changedSoon())})}countryOf(e){return this.countryEls.find(n=>n.el===e)??null}countryAt(e){let n=this.projection?.invert?.(e);if(!n||!Number.isFinite(n[0]))return null;let a=this.geo;return this.countryEls.find(r=>a.geoContains(r.feature,n))??null}hover(e){if(!this.projection||!this.tooltip||!this.readout)return;let n=this.pointOf(e),a=this.projection.invert?.(n),r=a&&Number.isFinite(a[0])&&(!Ke.has(this.projectionName)||this.geo.geoDistance([a[0],a[1]],[-this.projection.rotate()[0],-this.projection.rotate()[1]])<(Za[this.projectionName]??90)*Math.PI/180);this.readout.textContent=r?ge(a[1],We(a[0]),this.coordsFormat):"";let i=r?this.countryOf(e.target):null;for(let d of this.countryEls)d.el.classList.toggle("hover",d===i);if(!i||e.buttons){this.tooltip.hidden=!0;return}let s=this.input().items.find(d=>d.kind==="country"&&d.code.a3===i.code.a3),l=s&&s.kind==="country"&&s.value!==null?` \xB7 ${this.number(s.value)}`:"";this.tooltip.textContent=`${Ga(i.code.a2)} ${i.name}${l}`.trim();let c=this.stage.getBoundingClientRect();this.tooltip.style.left=`${e.clientX-c.left+14}px`,this.tooltip.style.top=`${e.clientY-c.top+14}px`,this.tooltip.hidden=!1}clickAt(e){let n=this.pointOf(e),a=this.projection?.invert?.(n);if(!a||!Number.isFinite(a[0]))return;if(this.flag("pick",!1)){let i=Wi(a[1]),s=Wi(We(a[0]));this.pins=[{lat:i,lon:s,label:ge(i,s,this.coordsFormat)}],this.build(this.geo),this.renderSide(),this.selectPoint({lat:i,lon:s},ge(i,s,this.coordsFormat));return}let r=this.countryOf(e.target)??this.countryAt(n);r&&this.selectCountry(r.code,!1)}selectPoint(e,n){this.announce(this.t("mapSelectedPoint",{label:n,coords:ge(e.lat,e.lon,this.coordsFormat)})),oe(this,ie.SELECT,{type:"point",label:n,lat:e.lat,lon:e.lon})}selectCountry(e,n){this.selected=this.selected===e.a3&&!n?null:e.a3;for(let l of this.countryEls)l.el.classList.toggle("selected",l.code.a3===this.selected);let a=Le(e,this.locale),r=this.input().items.find(l=>l.kind==="country"&&l.code.a3===e.a3),i=r&&r.kind==="country"?r.value:null,s=this.countryCenter(e);n&&s&&this.flyTo(s,this.countryZoom(e)),this.selected&&(this.announce(this.t("mapSelectedCountry",{name:a})),oe(this,ie.SELECT,{type:"country",label:a,code:e.a2||e.a3,a3:e.a3,value:i,lat:s?.lat,lon:s?.lon}))}mainland(e){let n=this.geo,a=n?.countries.find(s=>Bn(s.id,s.properties?.name).a3===e.a3);if(!a)return null;if(a.geometry.type!=="MultiPolygon")return a;let r=null,i=-1;for(let s of a.geometry.coordinates){let l={type:"Polygon",coordinates:s},c=n.geoArea(l);c>i&&([r,i]=[l,c])}return r}countryCenter(e){if(!this.geo)return null;let n=this.mainland(e);if(!n)return null;let[a,r]=this.geo.geoCentroid(n);return{lat:r,lon:a}}countryZoom(e){let n=this.mainland(e);if(!n)return 3;let a=this.geo.geoArea(n);return Math.min(14,Math.max(1.5,.9/Math.sqrt(a/(4*Math.PI))/4))}flyTo(e,n){let a={...this.viewState??this.initialView()},r={lon:e.lon,lat:Math.max(-85,Math.min(85,e.lat)),zoom:Math.min(Ya,Math.max(1,n))};if(cancelAnimationFrame(this.flight),typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches||!this.projection){this.viewState=r,this.update(),this.changed();return}let s=performance.now(),l=We(r.lon-a.lon),c=d=>{let p=Math.min(1,(d-s)/700),x=p<.5?4*p*p*p:1-(-2*p+2)**3/2;this.viewState={lon:We(a.lon+l*x),lat:a.lat+(r.lat-a.lat)*x,zoom:a.zoom*(r.zoom/a.zoom)**x},this.update(),p<1?this.flight=requestAnimationFrame(c):this.changed()};this.flight=requestAnimationFrame(c)}async find(e){let n=this.t,a=e.trim();if(!a||!this.geo)return;let r=a.match(/^(?:track|locate|traquer|localiser)\s+(.+)$/i);if(r){this.track(r[1]);return}let i=qe(a,this.locale),s=i?{country:i}:tt(a,this.locale);if(s&&"country"in s){this.selectCountry(s.country,!0),this.status(n("mapFoundCountry",{name:Le(s.country,this.locale)}));return}if(s&&"lat"in s){this.dropPin(s,s.name??ge(s.lat,s.lon,this.coordsFormat));return}if(s&&"address"in s){if(!this.getAttribute("geocoder")){this.status(n("mapNoGeocoder",{query:a}));return}this.status(n("mapGeocoding",{query:a}));let c=await this.geocode(a);c?this.dropPin(c,c.name||a):this.status(n("mapNotFound",{query:a}));return}this.status(n("mapNotFound",{query:a}))}trackButton(){let e=de({icon:"search",label:this.t("mapTrack"),key:"track",part:"track-button",onClick:()=>this.track(this.movieTarget())}),n=$("svg",{class:"icon",viewBox:"0 0 24 24",width:"16",height:"16",fill:"none",stroke:"currentColor","stroke-width":"2.1","stroke-linecap":"round","aria-hidden":"true"});return n.append($("circle",{cx:"12",cy:"12",r:"10"}),$("path",{d:"M22 12h-4M6 12H2M12 6V2M12 22v-4"}),$("circle",{cx:"12",cy:"12",r:"1.5"})),e.replaceChildren(n),e}movieTarget(){let e=this.getAttribute("movie")?.trim();if(e&&!/^(?:true|on|yes|1)$/i.test(e))return e;let n=this.input().items.find(a=>a.kind==="marker");if(n&&n.kind==="marker"){let a=this.locate(n.place);if(a)return`${this.markerLabel(n)}: ${a.lat}, ${a.lon}`}return"0, 0"}async track(e){let n=this.t;if(!this.geo||!this.stage)return!1;let a=e.match(/^([^:]{1,80}?)\s*:\s+(.+)$/),r=tt(a?a[2]:e,this.locale),i=null,s=(a?a[1]:e).trim();if(r&&"lat"in r)[i,s]=[r,a?s:r.name??s];else if(r&&"country"in r)[i,s]=[this.countryCenter(r.country),Le(r.country,this.locale)];else if(r&&"address"in r&&this.getAttribute("geocoder")){let y=await this.geocode(r.address);y&&(i=y)}if(!i)return this.status(n("mapNotFound",{query:s})),!1;let l=i;this.movie?.abort(),cancelAnimationFrame(this.flight);let c=new AbortController;this.movie=c;let{signal:d}=c;if(!Ke.has(this.projectionName)){this.projectionState="globe",this.viewState={lon:l.lon-70,lat:10,zoom:1},this.pins=[],this.redrawAll();let y=this.root.querySelector('[data-focus-key="projection"]');y&&(y.value="globe")}let p=this.hudView();this.stage.append(p.root),this.stage.classList.add("movie");let x=()=>c.abort(),b=y=>y.key==="Escape"&&x();this.root.addEventListener("keydown",b),p.stop.addEventListener("click",x),this.announce(n("mapTracking",{label:s}));let w=typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches,h=y=>{let N=()=>(Math.random()-.5)*y;p.coords.textContent=ge(l.lat+N(),l.lon+N()*2,"dms")};try{if(w)this.viewState={lon:l.lon,lat:Math.max(-85,Math.min(85,l.lat)),zoom:32},this.update();else{let N=[["ESTABLISHING SATELLITE UPLINK",1,1800,60],["SIGNAL ACQUIRED \u2014 TRIANGULATING",2.5,1700,20],["CROSS-REFERENCING RELAY NODES",6,1600,5],["ENHANCE",14,1400,1],["ENHANCE",32,1300,.1]];for(let[I,P,H,B]of N)p.log(I),await this.animateView({lon:l.lon,lat:l.lat,zoom:P},H,d,q=>h(B*(1-q)+B*.15))}if(d.aborted)throw new Error("stopped");h(0),p.log("TARGET LOCATED"),p.root.classList.add("locked"),this.input().items.some(N=>{let I=N.kind==="marker"?this.locate(N.place):null;return I&&Math.abs(I.lat-l.lat)<1e-4&&Math.abs(I.lon-l.lon)<1e-4})||(this.pins=[{lat:l.lat,lon:l.lon,label:s}],this.build(this.geo),this.stage.append(p.root)),this.renderSide(),this.announce(n("mapTargetLocated",{label:s,coords:ge(l.lat,l.lon,this.coordsFormat)})),oe(this,ie.SELECT,{type:"target",label:s,lat:l.lat,lon:l.lon}),this.changed(),await hu(6e3,d)}catch{}finally{this.root.removeEventListener("keydown",b),p.root.remove(),this.stage?.classList.remove("movie"),this.movie===c&&(this.movie=null)}return!0}hudView(){let e=g("ol",{class:"hud-log",attrs:{"aria-hidden":"true"}}),n=g("div",{class:"hud-coords",attrs:{"aria-hidden":"true"}}),a=g("button",{class:"hud-stop",attrs:{type:"button"},text:this.t("mapStop")}),r=g("div",{class:"hud-time",attrs:{"aria-hidden":"true"}});return r.textContent=`${new Date().toISOString().slice(0,19).replace("T"," ")} UTC`,{root:g("div",{class:"map-hud",part:"hud"},g("div",{class:"hud-scan",attrs:{"aria-hidden":"true"}}),g("div",{class:"hud-corners",attrs:{"aria-hidden":"true"}}),g("div",{class:"hud-reticle",attrs:{"aria-hidden":"true"}},g("span",{class:"hud-ring"}),g("span",{class:"hud-box"})),g("div",{class:"hud-top",attrs:{"aria-hidden":"true"}},g("span",{class:"hud-rec",text:"REC"}),g("span",{text:"SAT-7 // ORBITAL FEED"}),r),e,n,g("div",{class:"hud-locked",attrs:{"aria-hidden":"true"}},g("strong",{text:"TARGET LOCATED"})),a),coords:n,stop:a,log:s=>{for(e.append(g("li",{text:`> ${s}`}));e.children.length>5;)e.firstElementChild?.remove()}}}animateView(e,n,a,r){let i={...this.viewState??this.initialView()},s=We(e.lon-i.lon),l=Math.max(-85,Math.min(85,e.lat));return new Promise(c=>{let d=performance.now(),p=x=>{if(a.aborted)return c();let b=Math.min(1,(x-d)/n),w=b<.5?4*b*b*b:1-(-2*b+2)**3/2;this.viewState={lon:We(i.lon+s*w),lat:i.lat+(l-i.lat)*w,zoom:i.zoom*(e.zoom/i.zoom)**w},this.update(),r?.(b),b<1?this.flight=requestAnimationFrame(p):c()};this.flight=requestAnimationFrame(p)})}dropPin(e,n){this.pins=[{lat:e.lat,lon:e.lon,label:n}];let a=this.viewState??this.initialView();this.build(this.geo),this.renderSide(),this.flyTo(e,Math.max(a.zoom,Ke.has(this.projectionName)?2:4)),this.status(this.t("mapFound",{label:n,coords:ge(e.lat,e.lon,this.coordsFormat)})),this.selectPoint(e,n)}status(e){this.statusLine&&(this.statusLine.textContent=e)}async geocode(e,n){let a=e.toLowerCase(),r=nn.get(a);if(r==="none")return null;if(r&&r!=="pending")return r;let i=Gi(this.getAttribute("geocoder")??"",e,this.locale);if(!i)return null;try{let s=await fetch(i,{credentials:"omit",headers:{Accept:"application/json"},signal:n});if(!s.ok)throw new Error(String(s.status));let l=Hi(await s.json());return nn.set(a,l??"none"),l}catch(s){return s?.name!=="AbortError"&&nn.delete(a),null}}async geocodeItems(){let e=this.getAttribute("geocoder"),n=this.input().items.flatMap(r=>r.kind==="marker"&&"address"in r.place?[r.place.address]:r.kind==="route"?r.stops.flatMap(i=>"address"in i?[i.address]:[]):[]).filter(r=>!nn.has(r.toLowerCase())).slice(0,du);if(!e||!n.length)return;this.geocoding?.abort();let a=new AbortController;this.geocoding=a;for(let[r,i]of n.entries()){if(a.signal.aborted||(r&&await new Promise(s=>setTimeout(s,1e3)),await this.geocode(i,a.signal),a.signal.aborted))return;this.update(),this.renderSide()}}renderSide(){let e=this.t,{items:n}=this.input(),a=this.root.querySelector(".map-legend-host"),r=n.flatMap(l=>l.kind==="country"&&l.value!==null&&!l.color?[l.value]:[]);a&&(a.replaceChildren(),r.length&&a.append(g("div",{class:"map-legend",part:"legend",attrs:{role:"group","aria-label":e("mapLegend")}},g("span",{class:"map-legend-value",text:this.number(Math.min(...r))}),g("span",{class:"map-legend-bar",attrs:{"aria-hidden":"true"}}),g("span",{class:"map-legend-value",text:this.number(Math.max(...r))}))));let i=this.root.querySelector(".map-list-host");if(!i)return;i.replaceChildren();let s=[];for(let l of n)if(l.kind==="marker"){let c=this.locate(l.place),d=this.markerLabel(l),p="address"in l.place&&!c,x=c?ge(c.lat,c.lon,this.coordsFormat):this.getAttribute("geocoder")?e("mapLocating"):e("mapNeedsGeocoder");s.push(this.rowView("marker",d,x,l.color,c?()=>this.flyTo(c,Math.max((this.viewState??this.initialView()).zoom,4)):null,p))}else if(l.kind==="country"){let c=Le(l.code,this.locale),d=[l.code.a2||l.code.a3,l.value!==null?this.number(l.value):""].filter(Boolean).join(" \xB7 ");s.push(this.rowView("country",`${Ga(l.code.a2)} ${l.label||c}`.trim(),d,l.color,()=>this.selectCountry(l.code,!0),!1))}else if(l.kind==="route"){let c=l.stops.map(b=>this.locate(b)),d=l.stops.map(b=>"name"in b&&b.name?b.name:"address"in b?b.address:"country"in b?Le(b.country,this.locale):ge(b.lat,b.lon,this.coordsFormat)),p=0;for(let b=1;b<c.length;b++){let w=c[b-1],h=c[b];w&&h&&(p+=$i(w,h))}let x=c[0];s.push(this.rowView("route",l.label||d.join(" \u2192 "),p?e("mapDistance",{km:this.number(Math.round(p))}):"",l.color,x?()=>this.flyTo(x,2):null,!1))}else l.kind==="shape"&&s.push(this.rowView("shape",l.label||e("mapShape"),l.geometry.type,l.color,null,!1));for(let l of this.pins)s.push(this.rowView("pin",l.label,ge(l.lat,l.lon,this.coordsFormat),"",()=>this.flyTo(l,Math.max((this.viewState??this.initialView()).zoom,4)),!1));s.length&&i.append(g("ul",{class:"map-list",part:"list",attrs:{"aria-label":e("mapList")}},...s))}rowView(e,n,a,r,i,s){let l=this.t,c=g("span",{class:`map-swatch ${e}`,attrs:{"aria-hidden":"true"}});r&&c.style.setProperty("--map-item",r);let d=g("span",{class:"sr-only",text:`${l(`mapKind_${e}`)}: `}),p=i?g("button",{class:"map-item-go",attrs:{type:"button",title:l("mapShow",{label:n})},on:{click:i}},d,n):g("span",{class:"map-item-name"},d,n);return g("li",{class:`map-item ${e}${s?" pending":""}`},c,p,a?g("span",{class:"map-item-note",text:a}):null)}number(e){return new Intl.NumberFormat(this.locale,{maximumFractionDigits:2}).format(e)}report(){let e=[];for(let n of this.input().items)if(n.kind==="marker"){let a=this.locate(n.place);e.push(`${this.markerLabel(n)}: ${a?ge(a.lat,a.lon):"?"}`)}else n.kind==="country"?e.push(`${Le(n.code,this.locale)} (${n.code.a2||n.code.a3})${n.value!==null?`: ${n.value}`:""}`):n.kind==="route"&&e.push(n.stops.map(a=>{let r=this.locate(a);return r?ge(r.lat,r.lon):"?"}).join(" -> "));for(let n of this.pins)e.push(`${n.label}: ${ge(n.lat,n.lon)}`);return e.join(`
`)}geoJson(){let e=[];for(let n of this.input().items){let a={name:n.kind==="marker"?this.markerLabel(n):n.label||void 0,color:n.color||void 0};if(n.kind==="marker"){let r=this.locate(n.place);r&&e.push({type:"Feature",properties:a,geometry:{type:"Point",coordinates:[r.lon,r.lat]}})}else if(n.kind==="route"){let r=n.stops.map(i=>this.locate(i));r.every(Boolean)&&e.push({type:"Feature",properties:a,geometry:{type:"LineString",coordinates:r.map(i=>[i.lon,i.lat])}})}else if(n.kind==="shape")e.push({type:"Feature",properties:a,geometry:n.geometry});else if(n.kind==="country"){let r=this.geo?.countries.find(i=>Bn(i.id,i.properties?.name).a3===n.code.a3);e.push({type:"Feature",properties:{...a,name:Le(n.code,this.locale),code:n.code.a3,value:n.value??void 0},geometry:r?.geometry??null})}}for(let n of this.pins)e.push({type:"Feature",properties:{name:n.label},geometry:{type:"Point",coordinates:[n.lon,n.lat]}});return JSON.stringify({type:"FeatureCollection",features:e},null,2)}changed(){clearTimeout(this.changeTimer),oe(this,ie.CHANGE,this.view)}changedSoon(){clearTimeout(this.changeTimer),this.changeTimer=setTimeout(()=>oe(this,ie.CHANGE,this.view),300)}createEditor(){return this.editor?.destroy(),this.editor=new et({text:this.text??"",language:"plaintext",lineNumbers:!0,wrap:!0,highlightLimit:J().highlightLimit,label:this.heading||this.t("editor"),placeholder:this.getAttribute("placeholder")??void 0,onInput:e=>this.edited(e),onChange:e=>oe(this,ie.CHANGE,{value:e}),history:this.editHistory??void 0}),this.editor}contentEdited(){clearTimeout(this.previewTimer),this.previewTimer=setTimeout(()=>this.render(),300)}};function pu(t,e,n){if(n.a3==="ATA"||n.a3==="GRL")return"ice";if(new Set(["DZA","LBY","EGY","MRT","MLI","NER","TCD","SDN","ESH","SAU","YEM","OMN","ARE","QAT","KWT","IRQ","JOR","SYR","IRN","AFG","PAK","TKM","UZB","KAZ","MNG","NAM","BWA","AUS","DJI","SOM","SOL","ERI","ISR","PSE","TUN","MAR"]).has(n.a3))return"desert";let r=Ki.get(e);r===void 0&&(r=t.geoCentroid(e)[1],Ki.set(e,r));let i=Math.abs(r);return i>58?"tundra":i>35?"forest":i>20?"steppe":"tropic"}function hu(t,e){return new Promise(n=>{let a=setTimeout(n,t);e.addEventListener("abort",()=>{clearTimeout(a),n()})})}function We(t){return((t+180)%360+360)%360-180}function Wi(t){return Math.round(t*1e5)/1e5}function Yi(t){let[e,n]=[...t.values()];return Math.hypot(e[0]-n[0],e[1]-n[1])||1}var Un=`/*
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
`;var Zi=`/*
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
`;var Ji=`/*
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
`;var bu=200,yu=[["year",31536e3],["month",2592e3],["day",86400],["hour",3600],["minute",60],["second",1]],jn=class extends Je{static editorLanguage="json";constructor(){super(),this.editor=null,this.previewTimer=void 0}get now(){let e=this.getAttribute("now")?.trim();if(e){let n=/^\d+$/.test(e)?Number(e)*1e3:Date.parse(e);if(Math.abs(n)<=864e13)return n}return Date.now()}flag(e){return Ie(this.getAttribute(e))!==!1}relativeTime(e){let n=Math.round((e-this.now)/1e3),[a,r]=yu.find(([,s])=>Math.abs(n)>=s)??["second",1],i=Math.round(n/r);try{return new Intl.RelativeTimeFormat(this.locale,{numeric:"auto"}).format(i,a)}catch{return`${i} ${a}`}}formatDate(e,n={dateStyle:"medium",timeStyle:"short"}){try{return new Intl.DateTimeFormat(this.locale,n).format(e)}catch{return new Date(e).toISOString()}}previewPanel(e,n){let a=g("div",{class:"panel",attrs:{id:n}});if(!this.editing)return a.append(e),{panel:a,history:[]};let r=this.createEditor();return a.classList.add("data-edit"),a.append(g("div",{class:"body editor-body",part:"body source"},r.element),e),{panel:a,history:this.historyButtons(r)}}frameWith(e,n,a,{file:r,download:i=!0,badge:s="JSON"}){let{panel:l,history:c}=this.previewPanel(n,a);e.append(...this.chrome({badge:s,actions:[...c,this.editToggleButton(),this.fullscreenButton(),i&&this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(r),"application/json"):null,this.feature("copy")?this.copyButton(()=>this.text??""):null]}),l),this.editor?.align()}dataNotice(e){return Rt(e.error==="json"?this.t("jsonInvalid",{message:e.message}):this.t("dataNoList",{keys:e.message}))}createEditor(){this.editor?.destroy();let e=this.constructor;return this.editor=new et({text:this.text??"",language:e.editorLanguage,lineNumbers:!1,wrap:!0,highlightLimit:J().highlightLimit,label:this.heading||this.t("editor"),placeholder:this.getAttribute("placeholder")??void 0,onInput:n=>this.edited(n),onChange:n=>oe(this,ie.CHANGE,{value:n}),history:this.editHistory??void 0}),this.editor}contentEdited(){clearTimeout(this.previewTimer),this.previewTimer=setTimeout(()=>this.render(),bu)}};var vu=new Set(["number","compact","currency","percent","bytes","duration"]),xu=500;function _u(t){if(!Array.isArray(t))return[];let e=[];for(let n of t.slice(0,xu)){let a=Lt($e(n)?n.value??n.y:n);a!==null&&e.push({label:$e(n)?De(n.label??n.x,100):"",value:a})}return e}function wu(t,e){let n=Lt(t.change??t.delta);if(n!==null)return n;let a=Lt(t.previous);return a===null||e===null||a===0?null:(e-a)/Math.abs(a)*100}function Eu(t){let e=Lt(t.value),n=De(t.format,20).toLowerCase(),a=Lt(t.digits),r=De(t.good,10).toLowerCase();return{label:ga(t,["label","name","title"],200),value:e,display:e===null?De(t.value,100):"",format:vu.has(n)?n:"number",unit:De(t.unit,40),currency:/^[A-Za-z]{3}$/.test(De(t.currency,3))?De(t.currency,3).toUpperCase():"USD",digits:a!==null&&a>=0&&a<=6?Math.floor(a):null,change:wu(t,e),good:r==="down"||r==="none"?r:"up",against:ga(t,["against","period","compare"],100),description:De(t.description,500),url:Gr(t.url??t.href),series:_u(t.series??t.history??t.trend??t.spark)}}function Xa(t){let e=Vr(t,["stats","items","metrics","kpis"]);return e.ok?{ok:!0,stats:e.items.map(Eu).filter(n=>n.label||n.value!==null)}:e}function Xi(t,e){return t===0||e==="none"?"neutral":t>0==(e==="up")?"good":"bad"}function Qi(t,e,n,a){let r=t.map(l=>l.value),i=Math.min(...r),s=Math.max(...r)-i;return t.map((l,c)=>({x:t.length>1?a+c/(t.length-1)*(e-a*2):e/2,y:s?n-a-(l.value-i)/s*(n-a*2):n/2}))}var eo=Object.freeze({statsUp:"Up {change}",statsDown:"Down {change}",statsFlat:"No change",statsAgainst:"{change} {against}",statsHistory:"History of {name}",statsPoint:"Point {n}",statsEmpty:"No figures to show."}),to=Object.freeze({statsUp:"En hausse de {change}",statsDown:"En baisse de {change}",statsFlat:"Sans changement",statsAgainst:"{change} {against}",statsHistory:"Historique de {name}",statsPoint:"Point {n}",statsEmpty:"Aucun chiffre \xE0 afficher."});bn({en:eo,fr:to});var Au="http://www.w3.org/2000/svg",no=240,Qa=48,Tu=5;function Fn(t,e){let n=document.createElementNS(Au,t);for(let[a,r]of Object.entries(e))n.setAttribute(a,String(r));return n}var er=class extends jn{static type="stats";static componentAttributes=Object.freeze(["columns","trend","changes"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,download:!0,fullscreen:!0}};static styles=[Nt,Un,Zi,Ji];constructor(){super(),this.panelId=Ne("panel")}get stats(){let e=Xa(this.text??"");return e.ok?e.stats:[]}renderContent(e){let n=Xa(this.text??""),a=g("div",{class:"body data-body stats-body",part:"body"});if(!n.ok)a.append(this.dataNotice(n));else if(!n.stats.length)a.append(g("p",{class:"data-none",text:this.t("statsEmpty")}));else{let r=g("ul",{class:"stats-grid"},...n.stats.map((s,l)=>this.statView(s,l))),i=Number(this.getAttribute("columns"));Number.isInteger(i)&&i>=1&&i<=12&&r.style.setProperty("--_columns",String(i)),a.append(r)}this.frameWith(e,a,this.panelId,{file:"stats.json"})}statView(e,n){let a=g("span",{class:"stats-label",part:"label",text:e.label});return g("li",{class:"stats-tile",part:"stat"},e.url?g("a",{attrs:{href:e.url,rel:"noopener noreferrer"}},a):a,g("span",{class:"stats-value",part:"value",text:this.valueText(e,e.value)}),e.change!==null&&this.flag("changes")?this.changeView(e):null,e.series.length>1&&this.flag("trend")?this.trendView(e,n):null,e.description?g("p",{class:"stats-note",text:e.description}):null)}valueText(e,n){let a=n===null?e.display:this.formatValue(e,n);return e.unit?`${a} ${e.unit}`:a}formatValue(e,n){let a=e.digits===null?{}:{minimumFractionDigits:e.digits,maximumFractionDigits:e.digits};try{switch(e.format){case"compact":return this.number(n,{notation:"compact",maximumFractionDigits:1,...a});case"currency":return this.number(n,{style:"currency",currency:e.currency,...a});case"percent":return this.number(n/100,{style:"percent",maximumFractionDigits:1,...a});case"bytes":return this.bytes(n);case"duration":return this.duration(n);default:return this.number(n,a)}}catch{return String(n)}}number(e,n){return new Intl.NumberFormat(this.locale,n).format(e)}bytes(e){let n=["byte","kilobyte","megabyte","gigabyte","terabyte","petabyte"],a=Math.abs(e),r=Math.min(n.length-1,a<1?0:Math.floor(Math.log(a)/Math.log(1e3)));return this.number(e/1e3**r,{style:"unit",unit:n[r],unitDisplay:"short",maximumFractionDigits:1})}duration(e){let n=[["day",86400],["hour",3600],["minute",60],["second",1]],[a,r]=n.find(([,i])=>Math.abs(e)>=i)??n[3];return this.number(e/r,{style:"unit",unit:a,unitDisplay:"short",maximumFractionDigits:1})}changeView(e){let n=this.t,a=e.change,r=Xi(a,e.good),i=this.number(Math.abs(a)/100,{style:"percent",maximumFractionDigits:1}),s=n("statsFlat");return a>0?s=n("statsUp",{change:i}):a<0&&(s=n("statsDown",{change:i})),g("span",{class:`stats-change ${r}`,part:"change"},a?Ue(a>0?"chevron-up":"chevron-down"):null,g("span",{text:e.against?n("statsAgainst",{change:s,against:e.against}):s}))}trendView(e,n){let a=this.t,{series:r}=e,i=Qi(r,no,Qa,Tu),s=y=>`${r[y].label||a("statsPoint",{n:y+1})}: ${this.valueText(e,r[y].value)}`,l=r.length-1,c=Fn("polyline",{class:"stats-line",points:i.map(y=>`${y.x.toFixed(1)},${y.y.toFixed(1)}`).join(" ")}),d=Fn("line",{class:"stats-guide",y1:0,y2:Qa,x1:0,x2:0}),p=Fn("circle",{class:"stats-marker",r:4}),x=Fn("svg",{class:"stats-svg",viewBox:`0 0 ${no} ${Qa}`,"aria-hidden":"true"});x.append(d,c,p);let b=g("span",{class:"stats-point"}),w=g("div",{class:"stats-trend",part:"trend",attrs:{role:"slider",tabindex:"0","data-focus-key":`trend-${n}`,"aria-label":a("statsHistory",{name:e.label}),"aria-valuemin":"0","aria-valuemax":String(r.length-1)}},x),h=(y,N=!0)=>{l=y,p.setAttribute("cx",String(i[y].x)),p.setAttribute("cy",String(i[y].y)),d.setAttribute("x1",String(i[y].x)),d.setAttribute("x2",String(i[y].x)),w.classList.toggle("active",N),w.setAttribute("aria-valuenow",String(y)),w.setAttribute("aria-valuetext",s(y)),b.textContent=N?s(y):"\xA0"};return h(l,!1),w.addEventListener("pointermove",y=>{let N=w.getBoundingClientRect(),I=N.width?(y.clientX-N.left)/N.width:1;h(Math.max(0,Math.min(r.length-1,Math.round(I*(r.length-1)))))}),w.addEventListener("pointerleave",()=>h(r.length-1,this.root.activeElement===w)),w.addEventListener("focus",()=>h(l)),w.addEventListener("blur",()=>h(r.length-1,!1)),w.addEventListener("keydown",y=>{let N=Su(y.key,l,r.length);N!==null&&(y.preventDefault(),h(N))}),g("div",{class:"stats-history"},w,b)}};function Su(t,e,n){return t==="ArrowLeft"||t==="ArrowDown"?Math.max(0,e-1):t==="ArrowRight"||t==="ArrowUp"?Math.min(n-1,e+1):t==="Home"?0:t==="End"?n-1:null}function ao(t){return Kr(t,{keys:["code","content","source","text"],attributes:{language:"language",lang:"language",label:"label",filename:"label",file:"label",title:"label",highlightLines:"highlight-lines",highlight:"highlight-lines",startLine:"start-line",lineNumbers:"line-numbers",wrap:"wrap",tabSize:"tab-size"},otherwise:e=>({content:Ft(e),attributes:{language:"json"}})})}var ro={bash:"sh",css:"css",diff:"diff",javascript:"js",json:"json",markdown:"md",plaintext:"txt",python:"py",shell:"sh",typescript:"ts",xml:"html",yaml:"yml"},nr=class extends Je{static type="code";static fromData=ao;static dataAttributes=Object.freeze(["language","label","highlight-lines","start-line","line-numbers","wrap","tab-size"]);static componentAttributes=Object.freeze(["language","line-numbers","start-line","highlight-lines","wrap","wrap-toggle","collapsible","diff","tab-size"]);static presets={simple:{},full:{header:!0,dot:!0,copy:!0,search:!0,download:!0,"line-numbers":!0,"wrap-toggle":!0,fullscreen:!0}};static styles=[Nt,Un];constructor(){super(),this.wrapState=null,this.expanded=!1,this.editor=null,this._detected=void 0}attributeChangedCallback(e,n,a){e==="wrap"&&(this.wrapState=null),e==="collapsible"&&(this.expanded=!1),super.attributeChangedCallback(e,n,a)}contentChanged(){this.expanded=!1,this._detected=void 0}language(){let e=this.getAttribute("language")?.trim().toLowerCase()||"",n=this.text??"";if(e==="auto")return this._detected??=n.length<=J().highlightLimit?Ci(n):"plaintext",{name:this._detected,label:tr(this._detected)};if(this.feature("diff")&&!e)return{name:"plaintext",label:"diff"};let a=ki(e);return a?Mn(a)?{name:a,label:tr(a)}:(Ni(a).then(r=>r&&this.requestRender()),{name:"plaintext",label:tr(a)}):{name:"plaintext",label:e?e.slice(0,24):""}}get wrapped(){return this.wrapState??this.feature("wrap")}renderContent(e){let n=this.text??"",a=this.t,r=this.language();if(this.applyTabSize(e),this.editing){this.renderEditor(e,r);return}let i=On(n,{language:r.name,lineNumbers:this.feature("line-numbers"),startLine:fn(this.getAttribute("start-line"),{min:-1e9,max:1e9,fallback:1}),highlightRanges:ua(this.getAttribute("highlight-lines")),diff:this.feature("diff"),highlightLimit:J().highlightLimit,diffLabels:{added:a("added"),removed:a("removed")}}),s=fn(this.getAttribute("collapsible"),{min:1,max:1e5,fallback:0}),l=s>0&&i.lineCount>s+1&&!this.expanded,c=new Vt(i.code,{skip:".sign"}),d={run:b=>(b&&this.revealAll(e),c.run(b)),go:b=>Ha(c.go(b)),clear:()=>c.clear()},p=[this.searchButton(d),this.feature("wrap-toggle")?de({icon:"wrap",label:a("wrap"),key:"wrap",part:"wrap-button",pressed:this.wrapped,onClick:()=>{this.wrapState=!this.wrapped,this.render()}}):null,this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(`code.${ro[r.name]??"txt"}`),"text/plain"):null,this.feature("copy")?this.copyButton(()=>this.text??"",a("copyCode")):null],x=g("div",{class:"body",part:"body",attrs:{tabindex:"0",role:"region","aria-label":this.heading||`${a("code")}${r.label?` (${r.label})`:""}`}},i.element);if(e.classList.toggle("wrap",this.wrapped),e.classList.toggle("collapsed",l),l&&e.style.setProperty("--_collapse-lines",String(s)),e.append(...this.chrome({badge:r.label,actions:p})),i.highlightSkipped&&e.append(Rt(a("highlightSkipped"))),e.append(x),l){let b=g("div",{class:"more"},g("button",{class:"text-btn",part:"show-more",text:a("showMore",{count:yn(i.lineCount,this.locale)}),attrs:{type:"button","data-focus-key":"show-more","aria-expanded":"false"},on:{click:()=>{this.expanded=!0,this.render(),this.root.querySelector(".body")?.focus({preventScroll:!0})}}}));e.append(b)}}applyTabSize(e){let n=fn(this.getAttribute("tab-size"),{min:1,max:16,fallback:0});n?e.style.setProperty("--_tab-size",String(n)):e.style.removeProperty("--_tab-size")}renderEditor(e,n){let a=this.t,r=this.feature("diff")&&n.name==="plaintext",i=new et({text:this.text??"",language:r?"diff":n.name,lineNumbers:this.feature("line-numbers"),wrap:this.wrapped,highlightRanges:ua(this.getAttribute("highlight-lines")),highlightLimit:J().highlightLimit,label:this.heading||`${a("editor")}${n.label?` (${n.label})`:""}`,placeholder:this.getAttribute("placeholder")??void 0,onInput:p=>this.edited(p),onChange:p=>oe(this,ie.CHANGE,{value:p}),history:this.editHistory??void 0});this.editor?.destroy(),this.editor=i;let s=null,l={run:p=>(s=new Vt(i.layer.querySelector("pre.code")),s.run(p)),go:p=>Ha(s?.go(p)??null),clear:()=>s?.clear()},c=[this.searchButton(l),this.feature("wrap-toggle")?de({icon:"wrap",label:a("wrap"),key:"wrap",part:"wrap-button",pressed:this.wrapped,onClick:()=>{this.wrapState=!this.wrapped,this.render()}}):null,...this.historyButtons(i),this.editToggleButton(),this.fullscreenButton(),this.feature("download")?this.downloadButton(()=>this.text??"",this.downloadName(`code.${ro[n.name]??"txt"}`),"text/plain"):null,this.feature("copy")?this.copyButton(()=>this.text??"",a("copyCode")):null],d=g("div",{class:"body editor-body",part:"body"},i.element);e.classList.toggle("wrap",this.wrapped),e.classList.remove("collapsed"),e.append(...this.chrome({badge:n.label,actions:c}),d),i.align()}contentEdited(){this.searchOpen&&this.searchQuery&&this.searchBar?.run()}revealAll(e){e.classList.contains("collapsed")&&(this.expanded=!0,e.classList.remove("collapsed"),e.querySelector(".more")?.remove())}};function tr(t){return t==="plaintext"?"":t==="xml"?"HTML":(je.getLanguage(t)?.name??t).split(",")[0].trim()}export{nr as VtCode,Ja as VtMap,er as VtStats,Pr as configure};
/*! Bundled license information:

dompurify/dist/purify.es.mjs:
  (*! @license DOMPurify 3.4.17 | (c) Cure53 and other contributors | Released under the Apache license 2.0 and Mozilla Public License 2.0 | github.com/cure53/DOMPurify/blob/3.4.17/LICENSE *)
  (*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/babel/babel/blob/main/packages/babel-helpers/LICENSE *)
*/
