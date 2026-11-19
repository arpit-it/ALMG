// Local macOS NaturalLanguage adapter. Document text arrives on stdin, not argv.
// https://developer.apple.com/documentation/naturallanguage/nllanguagerecognizer
ObjC.import('Foundation');
ObjC.import('NaturalLanguage');
const data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
const text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding).js;
const documents = JSON.parse(text);
JSON.stringify(documents.map(function(document) {
  const recognizer = $.NLLanguageRecognizer.alloc.init;
  recognizer.processString(document);
  return ObjC.deepUnwrap(recognizer.languageHypothesesWithMaximum(3));
}));
