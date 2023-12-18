"""
Generates JSON format question-answer pairs and instructions for a Python file
Requirements:
[req01] The `DatasetGenerator` class shall:
        a. Accept Python file path, file details, base name, list of questions,
        and model configuration as input during instantiation.
        b. Initialize and store Python file path, file details, base name,
        question list, llm, and use_llm flag as class attributes.
        d. Provide `get_response_from_llm` method to retrieve llm response.
        e. Provide `process_question` method to process each question, generate
        corresponding responses, and add to the instruct_list.
        f. Provide `process_question_type` method to process questions
        related to the file, functions, classes, and methods.
        g. Provide `generate` method to generate responses for all questions
        and return the instruct_list.
        h. Internally manage question mapping to file details.
[req02] The `get_python_datasets` function shall:
        a. Accept a Python file path, file details, base name, questions list,
        and model config as input.
        b. Instantiate `DatasetGenerator` class using the provided input.
        c. Generate instruct_list using `DatasetGenerator` `generate` method.
        d. Return the generated `instruct_list`.
[req03] The `clean_and_get_unique_elements` function shall:
        a. Clean an input string (str) and return a string of unique elements.
"""
import logging
import re
import math
from typing import Dict, List, Tuple

def clean_and_get_unique_elements(input_str: str) -> str:
    """
    Clean input string and return string of unique elements.
    Args:
        input_str (str): The input string to be cleaned.
    Returns:
        str: The cleaned string.
    """
    cleaned_elements = set(re.sub(r'[^\w\-_>\s:/.]', '', element.strip())
                            for element in re.sub(r'\s+', ' ', input_str).split(','))
    return ', '.join(cleaned_elements)


class DatasetGenerator:
    """
    Generate JSON formatted dictionary outputs for a Python file.
    Attributes:
        file_path (str): The path to the Python file.
        file_details (Dict[str, Any]): Details of the Python file.
        base_name (str): The base name of the Python file.
        questions (List[Dict[str, str]]): Questions for generating responses.
        instruct_list (List[Dict[str, str]]): Storage for generated instructions.
        question_mapping (Dict[str, str]): Mapping of question types to keys in file details.
        use_llm (bool): Flag indicating if a language model should be used.
        llm (object): The language model for generating responses.
        prompt (str): The prompt format for querying the language model.
    Methods:
        add_to_list(list_to_update: List[Dict], query: str, response: str, 
        additional_field=None) -> List[Dict]: 
            Add response to the instruct list.
        get_response_from_llm(query: str, context: str) -> str:
            Get language model response to query for given context.
        process_question(question_type: str, question_id: str, query: str, 
        context: str, info: Dict) -> None:
            Process question and add generated response to the instruct_list.
        process_question_type(question_type: str, question_id: str, 
        question_text: str) -> None:
            Process question related to file, function, class, or method.
        generate() -> Tuple[List[Dict], List[Dict]]:
            Generate responses for all the questions and return the instruct_list.
    """

    def __init__(self, file_path: str, file_details: Dict, base_name: str,
                 questions: List[Dict], model_config: Dict) -> None:
        """
        Initialize the DatasetGenerator class.
        Args:
            file_path (str): The path to the Python file.
            file_details (Dict[str, Any]): Details of the Python file.
            base_name (str): The base name of the Python file.
            questions (List[Dict[str, str]]): Questions for generating responses.
            model_config (Dict): Configuration for the language model.
        Returns:
            None
        """
        self.file_path = file_path
        self.file_details = file_details
        self.base_name = base_name
        self.questions = questions
        self.model_config = model_config
        self.llm = model_config['model'] if 'model' in model_config else None 
        if self.llm is None:
            self.use_llm = False
        else:
            self.use_llm = True
        self.instruct_list = []
        self.question_mapping = {
            'file': 'file',
            'function': 'functions',
            'class': 'classes',
            'method': 'classes'
        }

    def add_to_list(
        self,
        list_to_update: List[Dict],
        query: str,
        response: str,
        additional_field=None
        ) -> List[Dict]:
        """
        Add response to the instruct list.
        Args:
            list_to_update (List[Dict]): The list to update.
            query (str): The query to be added.
            response (str): The response to be added.
            additional_field (Any): Additional field to be added.
        Returns:
            List[Dict]: The updated list.
        """
        list_to_update.append({'instruction': query, 'input': additional_field, 'output': response})
        return list_to_update

    def get_response_from_llm(self, query: str, context: str) -> str:
        """
        Get language model response to query for given context.
        Args:
            query (str): The query to be used for generating the response.
            context (str): The context to be used for generating the response.
        Returns:
            str: The generated response.
        """
        def get_context_and_prompt(query, context, code_qa):
            full_context = f"{context}\nCODE Q and A:\n{code_qa}"
            prompt = self.model_config['prompt_template'].format(context=full_context, query=query)
            context_size = len(self.llm.tokenize(prompt))
            return prompt, context_size

        max_context_length = self.model_config['inference_model']['model_params']['context_length']
        excluded_instructions = ["Call code graph", "Docstring"]
        code_qa = (
            "\n".join([f"Q: {item['instruction']} \nA: {item['output']}" 
            for item in self.instruct_list if not any(item['instruction'].startswith(prefix)
            for prefix in excluded_instructions)])
            )

        # manage context length for LLM starting with the longest and most comprehensive
        context_strategies = [
            lambda: '```python\n' + str(context) + '\n```',
            lambda: '```python\n' + str(self.file_details['file_info']['file_code_simplified']) + '\n```',
            lambda: self.get_string_from_info(self.file_details['file_info'], 'file_summary'),
            lambda: ''
        ]
        for strategy in context_strategies:
            context = strategy()
            prompt, context_size = get_context_and_prompt(query, context, code_qa)
            if context_size <= 0.70 * max_context_length:
                break
        else:
            logging.error(f'Model response failed, increase py2dataset_model_config.yaml context_length > {math.ceil(context_size/0.70)}')
            return ''

        try:
            response = re.sub(r'\n\s*\n', '\n\n', self.llm(prompt))
            logging.info(f'Response: {response}')
        except Exception as error:
            logging.error(f'Failed to generate model response: {error}')
            response = ''
        return response

    def process_question(self, question_type: str, question_id: str, query: str,
                         context: str, info: Dict) -> None:
        """
        Process question and add the generated response to the instruct_list.
        Args:
            question_type (str): The type of question to be processed.
            question_id (str): The ID of the question to be processed.
            query (str): The query to be processed.
            context (str): The context to be used for generating the response.
            info (Dict): The information of the Python file.
        Returns:
            None
        """
        if question_id.endswith('code_graph') or question_id.endswith('docstring'):
            response = info.get(question_id, {})
        else:
            response = (
                self.get_response_from_llm(query, context)
                if self.use_llm and question_id.endswith('purpose')
                else clean_and_get_unique_elements(str(info.get(question_id, '')))
                )
        if question_type == 'file':
            context = self.file_details['file_info']['file_code']
        if response and response != 'None':
            response_str = str(response).strip()
            if response_str:
                self.instruct_list.append({
                    'instruction': query,
                    'input': context,
                    'output': response_str
                })

    @staticmethod
    def get_string_from_info(info, item_type):
        """
        Get string from info dictionary.
        Args:
            info (Dict): The information of the Python file.
            item_type (str): The type of item to get the string from.
        Returns:
            str: The string from the info.
        """
        if info[item_type]:
            items = [item.strip() for item in str(info[item_type]).split(',') if item]
            return ', '.join(items)
        return ''

    def process_question_type(self, question_type: str, question_id: str,
                              question_text: str) -> None:
        """
        Process questions related to a file, function, class, or method.
        Args:
            question_type (str): The type of question to be processed.
            question_id (str): The ID of the question to be processed.
            question_text (str): The text of the question to be processed.
        Returns:
            None
        """
        if question_type == 'file':
            query = question_text.format(filename=self.base_name)
            info = self.file_details['file_info']
            context = self.file_details['file_info']['file_code']
            self.process_question(question_type, question_id, query, context, info)
        elif question_type == 'method':
            for class_name, class_info in self.file_details['classes'].items():
                for key, method_info in class_info.items():
                    if key.startswith('class_method_'):
                        method_name = key[len('class_method_'):]
                        context = method_info['method_code']
                        mapping = {'class_name': class_name, 'method_name': method_name}
                        query = question_text.format(filename=self.base_name, **mapping)
                        self.process_question(question_type, question_id, query, context, method_info)
        else:  # if question_type == 'function' or question_type == 'class'
            for name, info in self.file_details[self.question_mapping[question_type]].items():
                context = info[f'{question_type}_code']
                mapping = {f'{question_type}_name': name}
                if question_id == f'{question_type}_purpose' and self.use_llm:
                    variables_string = self.get_string_from_info(info, f'{question_type}_variables')
                    inputs_string = self.get_string_from_info(info, f'{question_type}_inputs')
                    combined_string = ', '.join([s for s in [variables_string, inputs_string] if s])
                    mapping[f'{question_type}_variables'] = clean_and_get_unique_elements(combined_string)
                    # get methods to include in mapping for query
                    if question_type == 'class':
                        methods_string = self.get_string_from_info(info, f'{question_type}_methods')
                        mapping[f'{question_type}_methods'] = methods_string

                query = question_text.format(filename=self.base_name, **mapping)
                self.process_question(question_type, question_id, query, context, info)

    def generate(self) -> Tuple[List[Dict], List[Dict]]:

        """
        Generate responses for all the questions and returns the instruct_list.
        Args:
            None
        Returns:
            Tuple[List[Dict], List[Dict]]: The generated question-answer pairs and instructions.
        """
        for question in self.questions:
            self.process_question_type(question['type'], question['id'], question['text'])
        return self.instruct_list


def get_python_datasets(file_path: str, file_details: Dict, base_name: str, questions: List[Dict],
                        model_config: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract information from a Python file and return it in JSON format.
    Args:
        file_path (str): The path to the Python file.
        file_details (Dict): The details of the file.
        base_name (str): The base Python code filename.
        questions (List[Dict]): The list of questions.
        llm (object): The language model to be used for generating responses.
        prompt (str): The prompt to be used for generating responses.
    Returns:
        Tuple[List[Dict], List[Dict]]: Extracted information in JSON format.
    """
    logging.info(f'I am at get_python_datasets.py at 288')
    generator = DatasetGenerator(file_path, file_details, base_name, questions, model_config)
    return generator.generate()
