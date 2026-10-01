// Explicit opt-in for isolated fixture runs on an existing system Chrome.
// Only ephemeral test profiles; never user tabs, downloads or installed profiles.
const executablePath=process.env.SMARTFLOW_TEST_CHROMIUM;
if(executablePath){
  const {chromium}=require('playwright');
  const launch=chromium.launch.bind(chromium);
  chromium.launch=options=>launch({executablePath,...options});
}
// Native extension fixtures need bundled Chromium, not branded Chrome (which
// disables unpacked-extension command-line loading). Empty profile means temp.
if(process.env.SMARTFLOW_TEST_EXTENSION_CHROMIUM){
  const {chromium}=require('playwright');
  const launch=chromium.launchPersistentContext.bind(chromium);
  chromium.launchPersistentContext=(profile,options)=>{
    if(profile!=='')throw Error('Native fixture requires an isolated temporary profile');
    return launch('',{...options,executablePath:process.env.SMARTFLOW_TEST_EXTENSION_CHROMIUM});
  };
}
