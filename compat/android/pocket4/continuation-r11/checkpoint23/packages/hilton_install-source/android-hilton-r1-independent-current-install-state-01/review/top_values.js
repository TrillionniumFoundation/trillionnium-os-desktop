function topValues(text){
 let i=0;function skip(){while(i<text.length&&/\s/.test(text[i]))i++;}
 function quoted(){const start=i++;while(i<text.length){if(text[i]==="\\"){i+=2;continue;}if(text[i++]==='"')return text.slice(start,i);}throw Error("JSON_STRING");}
 function value(){skip();const start=i;if(text[i]==='"'){quoted();return text.slice(start,i);}if(text[i]==="{"||text[i]==="["){const stack=[text[i++]=="{"?"}":"]"];while(stack.length){if(i>=text.length)throw Error("JSON_END");if(text[i]==='"'){quoted();continue;}const c=text[i++];if(c==="{")stack.push("}");else if(c==="[")stack.push("]");else if(c==="}"||c==="]"){if(stack.pop()!==c)throw Error("JSON_PAIR");}}return text.slice(start,i);}while(i<text.length&&!/[,}\]\s]/.test(text[i]))i++;return text.slice(start,i);}
 skip();if(text[i++]!="{")throw Error("TOP_OBJECT");const out={};for(;;){skip();if(text[i]==="}"){i++;break;}const key=JSON.parse(quoted());skip();if(text[i++]!==":")throw Error("COLON");if(key in out)throw Error("DUPLICATE");out[key]=value();skip();const c=text[i++];if(c==="}")break;if(c!==",")throw Error("COMMA");}skip();if(i!==text.length)throw Error("TAIL");return out;
}
