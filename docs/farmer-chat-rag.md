# Farmer Chat retrieval

Farmer Chat searches the bundled guidance library in English, Bangla and common romanized Bangla. The library covers potato and tomato scouting, produce and rice storage, field drainage, root-zone moisture, and selected BAMIS crop calendars. Each entry has an English and Bangla summary, a publisher URL, and topic, crop, district or stage restrictions where applicable.

At request time, the API filters the entries by scope and ranks keyword matches. The optional multilingual E5 encoder reranks eligible entries on the API host. Groq receives up to three passages alongside the existing chat evidence and returns a short answer. Links come from server-owned evidence. An answer that cites a retrieved passage appears as **AI reply with sources**. If the provider fails or returns an unusable answer, the app can show the most relevant published guidance directly.

The bundled statements are reference material. Plot forecasts and district advisories retain their own source and freshness labels. A photo still requires crop screening and field confirmation. The library covers selected cases, and source matching has been checked with example questions rather than validated in the field.

## Run and verify

The default backend installation includes the guidance library and keyword search. Set `GROQ_API_KEY` in the private backend environment to enable generated answers.

For optional semantic reranking, install `apps/api/requirements-rag.txt` in the API environment. Put the [tokenizer](https://huggingface.co/Xenova/multilingual-e5-small/blob/761b726/tokenizer.json) and [quantized CPU model](https://huggingface.co/Xenova/multilingual-e5-small/blob/761b726/onnx/model_int8.onnx) from the same revision in the same directory as `tokenizer.json` and `model_int8.onnx`. Set `FARMER_RAG_MODEL_DIR` to that directory, or use `work/rag-e5` in a local checkout. Restart the API after installing or replacing the files. The two assets use about 129 MiB on disk. Keyword search remains available when the model or its dependencies are missing.

From `apps/api`, run `python -m pytest -q tests/test_farmer_rag.py tests/test_farmer_chat.py tests/test_farmer_chat_sources.py`. For a manual browser check, open Farmer Chat and ask “What do concentric rings on older tomato leaves suggest?” Look for the scouting guidance and its publisher link. Then try “আলুর পাতার নিচে অনিয়মিত দাগ আর সাদা আবরণ দেখা যাচ্ছে। কী লক্ষণ মিলিয়ে দেখব?” and check the Bangla reply and late-blight source. An exact storage temperature question should report a verification gap.
