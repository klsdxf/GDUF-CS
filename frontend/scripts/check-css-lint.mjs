import stylelint from 'stylelint'
const result=await stylelint.lint({code:'.regression { color: #ffffff025; }',codeFilename:'src/redesign/reference.css',configFile:'.stylelintrc.json'})
if(!result.errored||!result.results.some(r=>r.warnings.some(w=>w.rule==='color-no-invalid-hex')))throw new Error('CSS lint failed to reject the audited invalid HEX')
