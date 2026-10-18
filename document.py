from langchain_community.document_loaders import DirectoryLoader, TextLoader
docs = DirectoryLoader("path/to/docs", glob="**/*.md",
                       loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"}).load()
# then the same MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter as before