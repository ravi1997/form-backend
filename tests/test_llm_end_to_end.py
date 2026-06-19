"""
tests/test_llm_end_to_end.py
End-to-end integration tests for LLM features.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app import create_app
from services.llm_service import LLMService
from services.llm_model_registry_service import LLMModelRegistryService
from services.llm_prompt_template_service import LLMPromptTemplateService
from services.llm_usage_tracking_service import LLMUsageTrackingService
from services.form_service import FormService
from engines.analysis_engine import AnalysisEngine
from models.llm_config import LLMConfig, LLMModel, PromptTemplate
from models.form import Form, FormCommit
from models.analysis import Analysis, AnalysisNode
from exceptions import LLMServiceError, QuotaExceededError


class TestLLMEndToEnd:
    """End-to-end test cases for LLM integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Initialize services
        self.llm_service = LLMService()
        self.model_registry = LLMModelRegistryService()
        self.template_service = LLMPromptTemplateService()
        self.usage_service = LLMUsageTrackingService()
        self.form_service = FormService()
        self.analysis_engine = AnalysisEngine()
        
        # Create test client
        self.client = self.app.test_client()
        
        # Create test user and get token
        self.test_user_id = 'test-user-123'
        self.test_org_id = 'test-org-123'
        self.headers = {'Authorization': f'Bearer test-token-{self.test_user_id}'}
        
    def teardown_method(self):
        """Clean up test fixtures."""
        self.app_context.pop()
        
    def test_complete_llm_form_generation_workflow(self):
        """Test complete workflow from form generation to saving."""
        
        # 1. Set up user quota
        self.usage_service.set_user_quota(self.test_user_id, 10000, 10.0)
        
        # 2. Register a test model
        model_data = {
            'model_id': 'gpt-3.5-turbo',
            'name': 'GPT-3.5 Turbo',
            'provider': 'openai',
            'max_tokens': 4096,
            'cost_per_1k_tokens': 0.002
        }
        self.model_registry.register_model(model_data)
        
        # 3. Create a form generation template
        template_data = {
            'name': 'Customer Feedback Form',
            'description': 'Template for generating customer feedback forms',
            'template': '''Generate a customer feedback form with the following requirements:
Topic: {{topic}}
Include rating: {{include_rating}}
Include comments: {{include_comments}}
Number of questions: {{num_questions}}

Return the form as a JSON structure with:
- title: Form title
- sections: Array of sections with questions
- ui: Basic UI configuration''',
            'variables': ['topic', 'include_rating', 'include_comments', 'num_questions'],
            'category': 'form_generation'
        }
        template = self.template_service.create_template(template_data)
        
        # 4. Generate form via API
        form_request = {
            'prompt': 'Create a customer feedback form',
            'template_id': template.template_id,
            'template_variables': {
                'topic': 'Customer Service',
                'include_rating': True,
                'include_comments': True,
                'num_questions': 5
            }
        }
        
        with patch.object(self.llm_service, 'generate_text') as mock_generate:
            mock_generate.return_value = {
                'text': json.dumps({
                    'title': 'Customer Service Feedback Form',
                    'sections': [
                        {
                            'title': 'Overall Experience',
                            'questions': [
                                {
                                    'type': 'rating',
                                    'label': 'How would you rate your overall experience?',
                                    'required': True
                                },
                                {
                                    'type': 'text',
                                    'label': 'Please provide any additional comments',
                                    'required': False
                                }
                            ]
                        }
                    ],
                    'ui': {
                        'theme': {
                            'primary_color': '#3b82f6'
                        }
                    }
                }),
                'usage': {
                    'prompt_tokens': 100,
                    'completion_tokens': 200,
                    'total_tokens': 300
                }
            }
            
            response = self.client.post(
                '/api/v1/llm/generate-form',
                json=form_request,
                headers=self.headers
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify form structure
            assert 'form_structure' in data
            form_structure = data['form_structure']
            assert form_structure['title'] == 'Customer Service Feedback Form'
            assert len(form_structure['sections']) > 0
            
            # Verify usage was tracked
            usage_stats = self.usage_service.get_usage_stats(self.test_user_id)
            assert usage_stats['total_tokens'] == 300
            assert usage_stats['request_count'] == 1
            
        # 5. Save the generated form
        form_data = {
            'title': form_structure['title'],
            'description': 'Generated by AI assistant',
            'org_id': self.test_org_id,
            'project_id': 'test-project-123',
            'schema': form_structure
        }
        
        form_response = self.client.post(
            '/api/v1/forms',
            json=form_data,
            headers=self.headers
        )
        
        assert form_response.status_code == 201
        saved_form = json.loads(form_response.data)
        
        # Verify form was saved
        assert saved_form['title'] == 'Customer Service Feedback Form'
        assert saved_form['org_id'] == self.test_org_id
        
    def test_llm_analysis_node_execution(self):
        """Test LLM analysis node execution in analysis pipeline."""
        
        # 1. Set up user quota
        self.usage_service.set_user_quota(self.test_user_id, 10000, 10.0)
        
        # 2. Register a test model
        model_data = {
            'model_id': 'gpt-3.5-turbo',
            'name': 'GPT-3.5 Turbo',
            'provider': 'openai',
            'max_tokens': 4096,
            'cost_per_1k_tokens': 0.002
        }
        self.model_registry.register_model(model_data)
        
        # 3. Create a test form with responses
        form = Form(
            title='Test Form',
            org_id=self.test_org_id,
            project_id='test-project-123',
            created_by=self.test_user_id
        )
        
        # Create a form commit
        commit = FormCommit(
            form_id=form.id,
            commit_id='test-commit-123',
            author_id=self.test_user_id,
            branch='main',
            message='Initial commit',
            schema={
                'sections': [
                    {
                        'title': 'Section 1',
                        'questions': [
                            {
                                'id': 'q1',
                                'type': 'text',
                                'label': 'What is your feedback?'
                            }
                        ]
                    }
                ]
            }
        )
        
        # Create test responses
        responses = [
            {
                'form_id': form.id,
                'commit_id': commit.commit_id,
                'org_id': self.test_org_id,
                'respondent_id': 'user-1',
                'answers': {
                    'q1': {
                        'value': 'Great service!',
                        'display_value': 'Great service!'
                    }
                }
            },
            {
                'form_id': form.id,
                'commit_id': commit.commit_id,
                'org_id': self.test_org_id,
                'respondent_id': 'user-2',
                'answers': {
                    'q1': {
                        'value': 'Could be better',
                        'display_value': 'Could be better'
                    }
                }
            }
        ]
        
        # 4. Create analysis with LLM node
        analysis = Analysis(
            title='Sentiment Analysis',
            org_id=self.test_org_id,
            project_id='test-project-123',
            created_by=self.test_user_id,
            graph={
                'nodes': [
                    {
                        'id': 'llm-node-1',
                        'type': 'llm_analysis',
                        'config': {
                            'model_id': 'gpt-3.5-turbo',
                            'prompt': 'Analyze the sentiment of the following feedback: {{feedback}}',
                            'output_format': 'json'
                        },
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'form-responses',
                        'type': 'form_responses',
                        'config': {
                            'form_id': form.id,
                            'commit_id': commit.commit_id
                        },
                        'position': {'x': 0, 'y': 0}
                    }
                ],
                'edges': [
                    {
                        'id': 'edge-1',
                        'source': 'form-responses',
                        'target': 'llm-node-1',
                        'source_port': 'output',
                        'target_port': 'input'
                    }
                ]
            }
        )
        
        # 5. Execute analysis
        with patch.object(self.llm_service, 'generate_text') as mock_generate:
            mock_generate.return_value = {
                'text': json.dumps({
                    'sentiment': 'positive',
                    'confidence': 0.8,
                    'summary': 'The feedback indicates overall satisfaction'
                }),
                'usage': {
                    'prompt_tokens': 50,
                    'completion_tokens': 100,
                    'total_tokens': 150
                }
            }
            
            # Mock form responses data
            with patch.object(self.form_service, 'get_form_responses') as mock_responses:
                mock_responses.return_value = responses
                
                # Execute analysis
                result = self.analysis_engine.execute_analysis(analysis)
                
                # Verify execution was successful
                assert result['status'] == 'completed'
                assert 'llm-node-1' in result['node_results']
                
                # Verify LLM node output
                llm_output = result['node_results']['llm-node-1']
                assert llm_output['status'] == 'completed'
                assert 'sentiment' in llm_output['data']
                
                # Verify usage was tracked
                usage_stats = self.usage_service.get_usage_stats(self.test_user_id)
                assert usage_stats['total_tokens'] == 150
                
    def test_conversational_form_assistant(self):
        """Test conversational form assistant workflow."""
        
        # 1. Set up user quota
        self.usage_service.set_user_quota(self.test_user_id, 10000, 10.0)
        
        # 2. Create a chat session
        session_response = self.client.post(
            '/api/v1/llm/chat/sessions',
            json={
                'title': 'Form Builder Assistant',
                'context_type': 'form_builder',
                'context_id': 'test-form-123'
            },
            headers=self.headers
        )
        
        assert session_response.status_code == 201
        session_data = json.loads(session_response.data)
        session_id = session_data['session_id']
        
        # 3. Send messages to assistant
        messages = [
            'I need to create a customer feedback form',
            'Add a rating question about overall satisfaction',
            'Also include a text area for detailed comments'
        ]
        
        with patch.object(self.llm_service, 'generate_text') as mock_generate:
            mock_generate.return_value = {
                'text': 'I understand. I\'ll help you create that form.',
                'usage': {
                    'prompt_tokens': 50,
                    'completion_tokens': 30,
                    'total_tokens': 80
                }
            }
            
            for message in messages:
                response = self.client.post(
                    f'/api/v1/llm/chat/sessions/{session_id}/messages',
                    json={'message': message},
                    headers=self.headers
                )
                
                assert response.status_code == 200
                data = json.loads(response.data)
                assert 'ai_response' in data
                assert 'usage' in data
                
        # 4. Get chat history
        history_response = self.client.get(
            f'/api/v1/llm/chat/sessions/{session_id}',
            headers=self.headers
        )
        
        assert history_response.status_code == 200
        history_data = json.loads(history_response.data)
        
        # Verify conversation history
        assert len(history_data['messages']) >= len(messages) + 1  # +1 for welcome message
        
        # Verify total usage
        total_tokens = sum(msg['usage']['total_tokens'] for msg in history_data['messages'] 
                          if msg['role'] == 'assistant' and 'usage' in msg)
        assert total_tokens == 80 * len(messages)  # Each response uses 80 tokens
        
    def test_quota_enforcement(self):
        """Test quota enforcement across LLM features."""
        
        # 1. Set up very low quota
        self.usage_service.set_user_quota(self.test_user_id, 10, 0.01)
        
        # 2. Try to generate form - should fail
        form_request = {
            'prompt': 'Create a form',
            'template_variables': {}
        }
        
        response = self.client.post(
            '/api/v1/llm/generate-form',
            json=form_request,
            headers=self.headers
        )
        
        assert response.status_code == 429  # Too Many Requests
        error_data = json.loads(response.data)
        assert 'quota' in error_data['error'].lower()
        
        # 3. Try to use chat assistant - should also fail
        session_response = self.client.post(
            '/api/v1/llm/chat/sessions',
            json={
                'title': 'Test Session',
                'context_type': 'test'
            },
            headers=self.headers
        )
        
        # Session creation should work (no quota check)
        assert session_response.status_code == 201
        session_data = json.loads(session_response.data)
        session_id = session_data['session_id']
        
        # But sending message should fail
        message_response = self.client.post(
            f'/api/v1/llm/chat/sessions/{session_id}/messages',
            json={'message': 'Hello'},
            headers=self.headers
        )
        
        assert message_response.status_code == 429
        
    def test_pii_scrubbing_in_llm_interactions(self):
        """Test PII scrubbing in LLM interactions."""
        
        # 1. Set up user quota
        self.usage_service.set_user_quota(self.test_user_id, 10000, 10.0)
        
        # 2. Send message with PII
        message_with_pii = 'Create a form for John Doe (john.doe@email.com, phone: 555-123-4567)'
        
        with patch.object(self.llm_service, 'generate_text') as mock_generate:
            # Verify that PII is scrubbed before sending to LLM
            def check_pii_scrubbed(**kwargs):
                prompt = kwargs.get('prompt', '')
                assert 'john.doe@email.com' not in prompt
                assert '555-123-4567' not in prompt
                assert '[EMAIL]' in prompt or '[PHONE]' in prompt
                
                return {
                    'text': 'Form created successfully',
                    'usage': {'total_tokens': 100}
                }
            
            mock_generate.side_effect = check_pii_scrubbed
            
            response = self.client.post(
                '/api/v1/llm/generate-form',
                json={'prompt': message_with_pii},
                headers=self.headers
            )
            
            assert response.status_code == 200
            
    def test_llm_analysis_node_error_handling(self):
        """Test error handling in LLM analysis nodes."""
        
        # 1. Set up user quota
        self.usage_service.set_user_quota(self.test_user_id, 10000, 10.0)
        
        # 2. Create analysis with LLM node
        analysis = Analysis(
            title='Error Test Analysis',
            org_id=self.test_org_id,
            project_id='test-project-123',
            created_by=self.test_user_id,
            graph={
                'nodes': [
                    {
                        'id': 'llm-node-error',
                        'type': 'llm_analysis',
                        'config': {
                            'model_id': 'gpt-3.5-turbo',
                            'prompt': 'This will cause an error',
                            'output_format': 'json'
                        }
                    }
                ],
                'edges': []
            }
        )
        
        # 3. Execute with mocked error
        with patch.object(self.llm_service, 'generate_text') as mock_generate:
            mock_generate.side_effect = LLMServiceError("API timeout")
            
            result = self.analysis_engine.execute_analysis(analysis)
            
            # Verify error is handled gracefully
            assert result['status'] == 'completed'  # Analysis completes even with node errors
            assert 'llm-node-error' in result['node_results']
            assert result['node_results']['llm-node-error']['status'] == 'failed'
            assert 'error' in result['node_results']['llm-node-error']


if __name__ == '__main__':
    pytest.main([__file__])