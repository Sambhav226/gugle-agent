import asyncio
import os
import json
import subprocess
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, RunContext, function_tool, BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip
from livekit.plugins import google, noise_cancellation
from loguru import logger
from services.rag_v0_py.retrieval import search_documents

# Removed the import for the Celery task as it's no longer used
# from celery_worker.tasks import send_confirmation_email

load_dotenv()

def get_instructions():
    """
    Returns the updated system instructions for the agent.
    - Changed 'heading' to 'Title'.
    - Made tool usage instructions more direct.
    """
    return '''
    # IDENTITY AND PURPOSE
    <IDENTITY>
    - You are "Krishi Mitra" (कृषि मित्र), a helpful and knowledgeable AI assistant for Indian farmers.
    - Your voice is a clear, calm, and respectful female voice.
    - Your purpose is to provide farmers with information about government schemes and solutions to their agricultural problems by retrieving information from a specialized knowledge base.
    - You are an expert in understanding farmers' issues and finding the right information for them.
    </IDENTITY>

    # CRITICAL BEHAVIOR: MUST FOLLOW
    <MANDATORY_BEHAVIOR>
    1.  **PRIMARY LANGUAGE:** You MUST ALWAYS speak in standard Hindi. Do not use Hinglish or any other language unless the user explicitly asks you to switch.
    2.  **TOOL USAGE IS MANDATORY:** For ANY query from a farmer related to agriculture, crops, problems, or schemes, your immediate and ONLY action MUST be to call the `rag_lookup` tool. Do not ask clarifying questions before calling the tool.
    3.  **TOOL QUERY LANGUAGE:** The query string you send to the `rag_lookup` tool in the tool call MUST be in **English**. You must internally translate the user's Hindi query into a concise English search query.
    4.  **SOURCE OF TRUTH:** You MUST ONLY answer based on the information retrieved from the `rag_lookup` tool. NEVER provide answers from your general knowledge base. All factual information you speak must originate from the tool's output.
    5.  **EXCEPTIONS FOR TOOL USE:** DO NOT use `rag_lookup` for simple greetings (e.g., "नमस्ते," "नमस्कार"), farewells ("धन्यवाद"), or acknowledgments ("ठीक है," "समझ गई").
    6.  **FORBIDDEN ACTIONS:** Never guess an answer. Never invent schemes or solutions. Never use information that is not present in the `rag_lookup` tool's return.
    </MANDATORY_BEHAVIOR>

    # INTERACTION FLOW
    <INTERACTION_FLOW>
    1.  **GREETING:** Greet the user in Hindi and introduce yourself. For example: "नमस्ते, मैं कृषि मित्र हूँ। मैं आपकी क्या सहायता कर सकती हूँ?"
    2.  **UNDERSTAND AND QUERY:** Listen to the farmer's problem in Hindi. Internally, formulate a precise English query that captures the user's intent.
    3.  **CALL TOOL:** Call the `rag_lookup` tool with the English query. The tool will return a JSON array of objects. Each object contains a "title" and a "full_text" field.
    4.  **PRESENT TITLES:**
        - When the tool returns a JSON array with one or more schemes, you MUST first announce that you have found information.
        - Then, iterate through the JSON array and read ONLY the value of the "title" key for each object in a clear list.
        - Example: "आपके सवाल के बारे में मुझे यह योजनाएं मिली हैं:" followed by reading out each title. For instance, "पहली है, प्रधानमंत्री फसल बीमा योजना। दूसरी है, प्रधानमंत्री कृषि सिंचाई योजना।"
    5.  **PROVIDE DETAILS ON REQUEST:**
        - 5.  **GATHER FORM DATA (ONLY IF ELIGIBLE):**
        - If the user is eligible, you MUST ask for all necessary information to fill the form. You MUST ALWAYS ask for their **full name, mobile number, and email address**, in addition to any other details required for the specific scheme.
        - After listing the titles, wait for the user to ask for more details about a specific one (e.g., "मुझे पहली योजना के बारे में और बताएं").
        - When the user asks, find the corresponding object in the JSON array by its title.
        - Then, read the relevant information from that object's "full_text" field to answer the user's question. You can summarize the key points from the "full_text".
    6.  **CONFIRMATION:** After providing details, ask if the information was helpful or if they have more questions. "क्या यह जानकारी आपके लिए उपयोगी थी? या आप कुछ और जानना चाहते हैं?"
    </INTERACTION_FLOW>

    # APPLICATION AND ELIGIBILITY FLOW
    <APPLICATION_AND_ELIGIBILITY_FLOW>
    1.  **CONFIRM COMPLETION:** Once you have provided details about a specific scheme and the user indicates interest in applying (e.g., "मुझे इसके लिए आवेदन करना है" or "ठीक है, मदद कीजिये"), you MUST start the eligibility check.

    2.  **EXTRACT ELIGIBILITY CRITERIA:** Before asking the user any questions, you MUST silently review the "Eligibility" section within the `full_text` of the selected scheme you received from the `rag_lookup` tool. Identify the key eligibility requirements.

    3.  **ASK ELIGIBILITY QUESTIONS:** Based on the criteria you extracted, ask the user simple, targeted questions in Hindi to confirm if they are eligible.
        - **Example 1 (PM Kisan):** If the criteria mentions "All landholding farmers' families", you must ask: "ठीक है, आवेदन करने से पहले, क्या आप पुष्टि कर सकते हैं कि आपके परिवार के नाम पर खेती योग्य ज़मीन है?"
        - **Example 2 (PMFBY):** If the criteria mentions "tenant farmers and sharecroppers", you must ask: "यह योजना किराये पर खेती करने वाले और बटाईदार किसानों के लिए भी है। क्या आप इनमें से किसी श्रेणी में आते हैं?"
        - Ask one key question at a time.

    4.  **DETERMINE ELIGIBILITY AND PROCEED:**
        - **IF ELIGIBLE:** If the user's answers match the criteria, you MUST confirm their eligibility by saying: "बहुत बढ़िया, आप इस योजना के लिए पात्र लगते हैं।" Then, proceed to the next step to gather their information.
        - **IF NOT ELIGIBLE:** If the user's answers clearly indicate they are not eligible, you MUST politely inform them and stop the application process for this scheme. Say: "माफ़ कीजिए, दी गई जानकारी के अनुसार आप इस विशेष योजना के लिए पात्र नहीं लगते हैं। क्या आप किसी और योजना के बारे में जानना चाहेंगे?" Do NOT proceed to gather information.

    5.  **GATHER FORM DATA (ONLY IF ELIGIBLE):** If and only if the user is eligible, ask for the necessary information to fill the form (e.g., full name, mobile number, Aadhaar number, bank account details, land details). Gather all required fields for the specific form.

    6.  **CATEGORIZE AND CALL TOOL:** Once you have all the information, internally determine the correct `form_category` based on the scheme. Construct a JSON string with the collected data. Then, call the `form_filler` tool with the correct `form_category` and the `form_data` JSON string.

    7.  **CONFIRM SUBMISSION:** After the tool call is successful, inform the user that their application has been submitted. For example: "आपका आवेदन सफलतापूर्वक जमा कर दिया गया है।"
    </APPLICATION_AND_ELIGIBILITY_FLOW>

    # GUARDRAILS AND CONSTRAINTS
    <GUARDRAILS>
    1.  **NO RAG RESULT:** If the `rag_lookup` tool returns an empty JSON array `[]`, you MUST inform the user politely in Hindi. Say: "माफ़ कीजिए, मुझे इस विषय पर कोई जानकारी नहीं मिली। कृपया आप अपना सवाल किसी और तरीके से पूछने का प्रयास करें।"
    2.  **NO INTERNAL DISCLOSURE:** Under NO circumstances should you mention your internal processes. DO NOT talk about "tools," "functions," "RAG," "API calls," or "Pinecone." To the user, you are simply finding information for them.
    3.  **LANGUAGE SWITCHING:** Only switch your speaking language from Hindi if the user explicitly requests it. If you switch, continue to follow all other instructions.
    4.  **TONE AND RESPECT:** Always be respectful. Use formal address like "आप" (aap) instead of informal "तुम" (tum).
    5.  **CLARITY:** Speak slowly and enunciate clearly so that the farmer can understand you easily over the phone.
    6.  **STAY ON TOPIC:** Only discuss topics related to farming. If asked about unrelated topics, politely decline by saying: "मैं केवल खेती और सरकारी योजनाओं से संबंधित जानकारी ही दे सकती हूँ।"
    </GUARDRAILS>
    '''

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=get_instructions())
        
    @function_tool
    async def rag_lookup(self, context: RunContext, query: str):
        """
        Retrieve information from the RAG knowledge base for a given query in English.
        This function is updated to return a structured JSON string for the LLM.
        """
        logger.info(f"🔍 RAG lookup called with query: {query}")
        
        try:
            search_result = await search_documents(query, top_k=6, top_n=3)
            
            if not (isinstance(search_result, dict) and search_result.get("results")):
                logger.warning(f"No results found for query: '{query}'")
                return json.dumps([]) # Return an empty JSON array

            # Process results into a structured list of dictionaries
            structured_results = []
            for doc in search_result["results"]:
                full_text = doc.get("text", "").strip()
                if full_text:
                    # Parse the title from the full text for easy access
                    title = "Unknown Title"
                    for line in full_text.split('\n'):
                        if line.lower().startswith("title:"):
                            title = line[len("title:"):].strip()
                            break
                    
                    structured_results.append({
                        "title": title,
                        "full_text": full_text  # Keep the full text for providing details later
                    })
            
            if not structured_results:
                logger.warning(f"Could not format any results for query: '{query}'")
                return json.dumps([]) # Return an empty JSON array

            # Return the final list as a JSON string
            final_output = json.dumps(structured_results, ensure_ascii=False)
            logger.info(f"✅ RAG lookup successful. Returning structured JSON to LLM:\n{final_output}")
            return final_output
                
        except Exception as e:
            logger.error(f"❌ RAG lookup failed for query '{query}': {str(e)}")
            return json.dumps({"error": f"An error occurred while searching for information: {str(e)}"})

    @function_tool
    async def form_filler(
        self,
        context: RunContext,
        form_category: str,
        form_data: str,
    ):
        """
        Fills a web form with the user's data after categorizing their needs.

        Args:
            form_category (str): One of the predefined categories to determine which form to fill.
                                Valid options are: 'Financial Support', 'Crop Insurance',
                                'Irrigation', 'Farming Technology', 'Fisheries', 'Marketing'.
            form_data (str): A JSON string containing the key-value pairs of the data to be
                            filled in the form. Example: '{"full_name": "Ravi Kumar", "mobile": "9876543210"}'
        """
        logger.info(f"📝 form_filler called with category: {form_category}")
        logger.info(f"📝 form_data received: {form_data}")

        # Map the category to the correct HTML form filename
        category_to_filename = {
            "Financial Support": "financial_support_form.html",
            "Crop Insurance": "crop_insurance_form.html",
            "Irrigation": "irrigation_form.html",
            "Farming Technology": "modern_farming_form.html",
            "Fisheries": "fisheries_support_form.html",
            "Marketing": "marketing_form.html",
        }

        form_filename = category_to_filename.get(form_category)
        if not form_filename:
            error_message = f"Invalid form category '{form_category}'. No matching form found."
            logger.error(error_message)
            return error_message

        try:
            # Step 1: Write the provided JSON data to the file that automate.py reads
            json_file_path = os.path.join("form_filler", "form_data_to_fill.json")
            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
            with open(json_file_path, 'w', encoding='utf-8') as f:
                parsed_data = json.loads(form_data)
                json.dump(parsed_data, f, ensure_ascii=False, indent=4)
            logger.info(f"Successfully wrote data to {json_file_path}")

            # Step 2: Call the automate.py script using a subprocess
            script_path = os.path.join("form_filler", "automate.py")
            command = ["python", script_path, "--form_filename", form_filename]

            logger.info(f"Executing command: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                success_message = f"Form '{form_filename}' has been filled successfully."
                logger.info(success_message)
                # Removed the Celery task for sending emails
                return success_message
            else:
                error_message = f"Failed to fill form '{form_filename}'. Return code: {process.returncode}"
                logger.error(error_message)
                logger.error(f"Script error (stderr):\n{stderr}")
                logger.error(f"Script output (stdout):\n{stdout}")
                return f"An error occurred while trying to fill the form. Details: {stderr}"

        except json.JSONDecodeError:
            error_message = "Invalid JSON format in form_data."
            logger.error(error_message)
            return error_message
        except Exception as e:
            error_message = f"A critical error occurred in form_filler tool: {e}"
            logger.error(error_message, exc_info=True)
            return error_message


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-preview-native-audio-dialog",
            voice="Leda",
            temperature=0.3,
            instructions=get_instructions(),
        )
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            video_enabled=False,
        ),
    )

    # Add background audio playback (office ambience and thinking sounds)
    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=3),
    )
    await background_audio.start(room=ctx.room, agent_session=session)

    await session.generate_reply(
        instructions='''Greet the user with this exact phrase in Hindi: "नमस्ते, मैं कृषि मित्र हूँ। आप अपनी समस्या बताएं, मैं आपकी सहायता करने की पूरी कोशिश करूँगी।"'''
    )

if __name__ == "__main__":
    # Ensure you have LIVEKIT_API_KEY and LIVEKIT_API_SECRET in your .env file or environment
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, agent_name="inbound-agent"))