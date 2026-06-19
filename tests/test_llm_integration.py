"""
tests/test_llm_integration.py
Tests for LLM integration components.
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
from models.llm_config import LLMConfig, LLMModel, PromptTemplate
from exceptions import LLMServiceError, QuotaExceededError


class TestLLMService:
    """Test cases for LLM service."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.llm_service = LLMService()
        
    def test_get_available_models(self):
        """Test getting available LLM models."""
        with self.app.app_context():
            models = self.llm_service.get_available_models()
            assert isinstance(models, list)
            assert len(models) > 0
            assert all('model_id' in model for model in models)
            
    @patch('services.llm_service.LLMService._call_llm_provider')
    def test_generate_text_success(self, mock_call):
        """Test successful text generation."""
        mock_call.return_value = {
            'text': 'Generated text',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
            'model': 'gpt-3.5-turbo'
        }
        
        with self.app.app_context():
            result = self.llm_service.generate_text(
                model_id='gpt-3.5-turbo',
                prompt='Test prompt',
                max_tokens=100
            )
            
            assert result['text'] == 'Generated text'
            assert result['usage']['total_tokens'] == 30
            
    @patch('services.llm_service.LLMService._call_llm_provider')
    def test_generate_text_error(self, mock_call):
        """Test text generation error handling."""
        mock_call.side_effect = LLMServiceError("API error")
        
        with self.app.app_context():
            with pytest.raises(LLMServiceError):
                self.llm_service.generate_text(
                    model_id='gpt-3.5-turbo',
                    prompt='Test prompt'
                )
                
    def test_validate_prompt(self):
        """Test prompt validation."""
        with self.app.app_context():
            # Valid prompt
            assert self.llm_service._validate_prompt('Valid prompt') is True
            
            # Empty prompt
            with pytest.raises(LLMServiceError):
                self.llm_service._validate_prompt('')
                
            # Too long prompt
            long_prompt = 'x' * 100000
            with pytest.raises(LLMServiceError):
                self.llm_service._validate_prompt(long_prompt)


class TestLLMModelRegistryService:
    """Test cases for LLM model registry service."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.registry_service = LLMModelRegistryService()
        
    def test_register_model(self):
        """Test model registration."""
        model_data = {
            'model_id': 'test-model',
            'name': 'Test Model',
            'provider': 'openai',
            'max_tokens': 4096,
            'cost_per_1k_tokens': 0.002
        }
        
        with self.app.app_context():
            model = self.registry_service.register_model(model_data)
            assert model.model_id == 'test-model'
            assert model.name == 'Test Model'
            
    def test_get_model(self):
        """Test getting a model by ID."""
        with self.app.app_context():
            # First register a model
            model_data = {
                'model_id': 'test-model',
                'name': 'Test Model',
                'provider': 'openai',
                'max_tokens': 4096,
                'cost_per_1k_tokens': 0.002
            }
            self.registry_service.register_model(model_data)
            
            # Then retrieve it
            model = self.registry_service.get_model('test-model')
            assert model is not None
            assert model.model_id == 'test-model'
            
    def test_list_models(self):
        """Test listing all models."""
        with self.app.app_context():
            # Register a few models
            models_data = [
                {'model_id': 'model1', 'name': 'Model 1', 'provider': 'openai'},
                {'model_id': 'model2', 'name': 'Model 2', 'provider': 'anthropic'},
            ]
            
            for data in models_data:
                self.registry_service.register_model(data)
                
            models = self.registry_service.list_models()
            assert len(models) >= 2
            
    def test_update_model(self):
        """Test updating a model."""
        with self.app.app_context():
            # Register a model
            model_data = {
                'model_id': 'test-model',
                'name': 'Test Model',
                'provider': 'openai',
                'max_tokens': 4096,
                'cost_per_1k_tokens': 0.002
            }
            self.registry_service.register_model(model_data)
            
            # Update it
            update_data = {
                'name': 'Updated Model',
                'max_tokens': 8192
            }
            updated_model = self.registry_service.update_model('test-model', update_data)
            
            assert updated_model.name == 'Updated Model'
            assert updated_model.max_tokens == 8192


class TestLLMPromptTemplateService:
    """Test cases for LLM prompt template service."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.template_service = LLMPromptTemplateService()
        
    def test_create_template(self):
        """Test creating a prompt template."""
        template_data = {
            'name': 'Form Generation Template',
            'description': 'Template for generating forms',
            'template': 'Generate a form about {{topic}}',
            'variables': ['topic'],
            'category': 'form_generation'
        }
        
        with self.app.app_context():
            template = self.template_service.create_template(template_data)
            assert template.name == 'Form Generation Template'
            assert template.variables == ['topic']
            
    def test_render_template(self):
        """Test rendering a template with variables."""
        with self.app.app_context():
            # Create a template
            template_data = {
                'name': 'Test Template',
                'description': 'Test template',
                'template': 'Hello {{name}}, welcome to {{place}}!',
                'variables': ['name', 'place'],
                'category': 'test'
            }
            template = self.template_service.create_template(template_data)
            
            # Render it
            rendered = self.template_service.render_template(
                template.template_id,
                {'name': 'John', 'place': 'Paris'}
            )
            
            assert rendered == 'Hello John, welcome to Paris!'
            
    def test_get_template(self):
        """Test getting a template by ID."""
        with self.app.app_context():
            # Create a template
            template_data = {
                'name': 'Test Template',
                'description': 'Test template',
                'template': 'Test content',
                'variables': [],
                'category': 'test'
            }
            created_template = self.template_service.create_template(template_data)
            
            # Retrieve it
            template = self.template_service.get_template(created_template.template_id)
            assert template is not None
            assert template.name == 'Test Template'


class TestLLMUsageTrackingService:
    """Test cases for LLM usage tracking service."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.usage_service = LLMUsageTrackingService()
        
    def test_track_usage(self):
        """Test tracking LLM usage."""
        usage_data = {
            'user_id': 'test-user',
            'org_id': 'test-org',
            'model_id': 'gpt-3.5-turbo',
            'prompt_tokens': 10,
            'completion_tokens': 20,
            'total_tokens': 30,
            'cost': 0.0006
        }
        
        with self.app.app_context():
            usage_record = self.usage_service.track_usage(usage_data)
            assert usage_record.user_id == 'test-user'
            assert usage_record.total_tokens == 30
            
    def test_check_quota(self):
        """Test checking user quota."""
        with self.app.app_context():
            # Set up a user with quota
            self.usage_service.set_user_quota('test-user', 10000, 10.0)
            
            # Check quota
            quota_info = self.usage_service.check_quota('test-user')
            assert quota_info['limit_tokens'] == 10000
            assert quota_info['limit_cost'] == 10.0
            
    def test_check_quota_exceeded(self):
        """Test quota exceeded scenario."""
        with self.app.app_context():
            # Set up a user with small quota
            self.usage_service.set_user_quota('test-user', 10, 0.01)
            
            # Use some tokens
            self.usage_service.track_usage({
                'user_id': 'test-user',
                'org_id': 'test-org',
                'model_id': 'gpt-3.5-turbo',
                'prompt_tokens': 5,
                'completion_tokens': 6,
                'total_tokens': 11,
                'cost': 0.0002
            })
            
            # Check quota - should raise exception
            with pytest.raises(QuotaExceededError):
                self.usage_service.check_quota('test-user')
                
    def test_get_usage_stats(self):
        """Test getting usage statistics."""
        with self.app.app_context():
            # Track some usage
            for i in range(5):
                self.usage_service.track_usage({
                    'user_id': 'test-user',
                    'org_id': 'test-org',
                    'model_id': 'gpt-3.5-turbo',
                    'prompt_tokens': 10,
                    'completion_tokens': 20,
                    'total_tokens': 30,
                    'cost': 0.0006
                })
                
            stats = self.usage_service.get_usage_stats('test-user')
            assert stats['total_tokens'] == 150
            assert stats['total_cost'] == 0.003
            assert stats['request_count'] == 5


class TestLLMAPIRoutes:
    """Test cases for LLM API routes."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Create a test user and get token
        with self.app.app_context():
            # This would normally involve creating a user and getting a JWT token
            # For testing, we'll use a mock token
            self.headers = {'Authorization': 'Bearer test-token'}
            
    def test_get_llm_config(self):
        """Test getting LLM configuration."""
        response = self.client.get('/api/v1/llm/config', headers=self.headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'models' in data
        assert 'templates' in data
        
    def test_update_llm_config(self):
        """Test updating LLM configuration."""
        config_data = {
            'default_model': 'gpt-3.5-turbo',
            'max_tokens': 1000,
            'temperature': 0.7
        }
        
        response = self.client.put(
            '/api/v1/llm/config',
            json=config_data,
            headers=self.headers
        )
        
        # Should be 200 or 403 depending on permissions
        assert response.status_code in [200, 403]
        
    def test_generate_form(self):
        """Test form generation endpoint."""
        form_request = {
            'prompt': 'Create a customer feedback form',
            'options': {
                'include_rating': True,
                'include_comments': True
            }
        }
        
        response = self.client.post(
            '/api/v1/llm/generate-form',
            json=form_request,
            headers=self.headers
        )
        
        # Should be 200 or 403 depending on permissions and quota
        assert response.status_code in [200, 403, 429]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'form_structure' in data
            assert 'title' in data['form_structure']
            
    def test_chat_with_assistant(self):
        """Test chat assistant endpoint."""
        chat_request = {
            'message': 'How do I add a rating question?'
        }
        
        response = self.client.post(
            '/api/v1/llm/chat',
            json=chat_request,
            headers=self.headers
        )
        
        # Should be 200 or 403 depending on permissions and quota
        assert response.status_code in [200, 403, 429]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'response' in data
            assert 'usage' in data


if __name__ == '__main__':
    pytest.main([__file__])