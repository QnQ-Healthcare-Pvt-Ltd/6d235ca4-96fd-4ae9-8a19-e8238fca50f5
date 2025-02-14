
import React, { useState, useEffect, useRef } from 'react';
import styles from './VisaApplicationFormComponent.module.css';
import { z } from 'zod';

type StatusType = 'success' | 'error' | 'info' | '';

interface ValidationRule {
  field_id: string;
  generated_code: string;
  prompt?: string;
  description?: string;
}

interface VisaApplicationFormComponentData {
  applicant_full_name: string;
  applicant_email: string;
  passport_number: string;
  date_of_birth: string;
  nationality: string;
  travel_dates: string;
  visa_type: string;
  additional_documents: string;
}

interface VisaApplicationFormComponentProps {
  onSubmit: (data: VisaApplicationFormComponentData) => void;
  initialData?: Partial<VisaApplicationFormComponentData>;
}

interface FormStatus {
  type: StatusType;
  message: string;
}

const validationRules: ValidationRule[] = [];

export default function VisaApplicationFormComponent({ onSubmit, initialData = {} }: VisaApplicationFormComponentProps) {
  const [formData, setFormData] = useState<Partial<VisaApplicationFormComponentData>>(initialData);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<FormStatus>({ type: '', message: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [filePreview, setFilePreview] = useState<Record<string, string>>({});
  const submissionInProgress = useRef<boolean>(false);

  // Clear status message after 5 seconds if it's a success message
  useEffect(() => {
    if (status.type === 'success') {
      const timer = setTimeout(() => {
        setStatus({ type: '', message: '' });
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [status]);

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(filePreview).forEach(url => URL.revokeObjectURL(url));
    };
  }, []);

  const validateField = (value: string, fieldId: string, fieldType?: string): string => {
    // If no validation rules exist for this field, return empty string (no error)
    const fieldRules = validationRules.filter(rule => rule.field_id === fieldId);
    if (!fieldRules || fieldRules.length === 0) return '';

    // Apply each validation rule
    for (const rule of fieldRules) {
      try {
        const validationFn = new Function('value', `
          try {
            const result = (function(value) {
              ${rule.generated_code}
            })(value);
            return result;
          } catch (e) {
            console.error('Validation execution error:', e);
            return true; // Fail open on execution error
          }
        `);

        const isValid = validationFn(value);
        if (!isValid) {
          return rule.prompt || rule.description || 'Invalid input';
        }
      } catch (e) {
        console.error('Validation creation error:', e);
      }
    }
    return ''; // No validation errors
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    
    // Handle select-multiple type
    const inputType = (e.target as HTMLSelectElement).multiple ? 'select-multiple' : type;
    const error = validateField(value, name, inputType);
    
    setFormData(prev => ({ ...prev, [fieldKey]: value }));
    
    if (error) {
      setErrors(prev => ({ ...prev, [name]: error }));
    } else {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Prevent duplicate submissions
    if (submissionInProgress.current || isSubmitting) {
      console.log('Submission already in progress');
      return;
    }

    setIsSubmitting(true);
    submissionInProgress.current = true;
    setStatus({ type: '', message: '' });

    try {
      // Validate all fields
      const newErrors: Record<string, string> = {};
      let hasErrors = false;

      Object.entries(formData).forEach(([fieldKey, value]) => {
        const fieldId = fieldKey.replace(/_/g, '-');
        const error = validateField(value as string, fieldId);
        if (error) {
          hasErrors = true;
          newErrors[fieldId] = error;
        }
      });

      if (hasErrors) {
        setErrors(newErrors);
        setStatus({
          type: 'error',
          message: 'Please correct the form errors'
        });
        return;
      }

      // Process form submission
      await onSubmit(formData as VisaApplicationFormComponentData);
      setStatus({
        type: 'success',
        message: 'Form submitted successfully!'
      });
      setErrors({});

      // Reset form after successful submission
      setTimeout(() => {
        setFormData({});
      }, 5000);

    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Failed to submit form'
      });
    } finally {
      setIsSubmitting(false);
      submissionInProgress.current = false;
    }
  };

  const handleSingleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    const value = checked.toString();
    
    const error = validateField(value, name, 'checkbox');
    
    setFormData(prev => ({ ...prev, [fieldKey]: value }));
    
    if (error) {
      setErrors(prev => ({ ...prev, [name]: error }));
    } else {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const handleMultiCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, checked } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    
    setFormData(prev => {
      const currentValues = (prev[fieldKey] as string || '').split(',').filter(Boolean);
      const newValues = checked
        ? [...currentValues, value]
        : currentValues.filter(v => v !== value);
      const newValue = newValues.join(',');
      
      const error = validateField(newValue, name, 'multiple');
      
      if (error) {
        setErrors(prev => ({ ...prev, [name]: error }));
      } else {
        setErrors(prev => {
          const newErrors = { ...prev };
          delete newErrors[name];
          return newErrors;
        });
      }
      
      return {
        ...prev,
        [fieldKey]: newValue
      };
    });
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, files } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    
    if (files && files.length > 0) {
      const file = files[0];
      
      // Create preview URL for images
      if (file.type.startsWith('image/')) {
        const previewUrl = URL.createObjectURL(file);
        setFilePreview(prev => ({
          ...prev,
          [fieldKey]: previewUrl
        }));
      }

      // Convert file to base64 for form data
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result as string;
        setFormData(prev => ({
          ...prev,
          [fieldKey]: base64String
        }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleRichTextFormat = (command: string) => {
    document.execCommand(command, false);
  };

  const handleRichTextChange = (e: React.FormEvent<HTMLDivElement>, fieldId: string) => {
    const content = e.currentTarget.innerHTML;
    const fieldKey = fieldId.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    setFormData(prev => ({ ...prev, [fieldKey]: content }));
  };

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    const formatted = formatPhoneNumber(value);
    setFormData(prev => ({ ...prev, [fieldKey]: formatted }));
  };

  const formatPhoneNumber = (value: string) => {
    const cleaned = value.replace(/\D/g, '');
    const match = cleaned.match(/^(\d{0,3})(\d{0,3})(\d{0,4})$/);
    if (match) {
      return !match[2] ? match[1] 
        : !match[3] ? `(${match[1]}) ${match[2]}`
        : `(${match[1]}) ${match[2]}-${match[3]}`;
    }
    return value;
  };

  const handleCurrencyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const fieldKey = name.replace(/-/g, '_') as keyof VisaApplicationFormComponentData;
    const formatted = parseFloat(value).toFixed(2);
    setFormData(prev => ({ ...prev, [fieldKey]: formatted }));
  };

  return (
    <div className={styles['form-container-wrapper']}>
      <form 
        onSubmit={handleSubmit} 
        className={styles['form-container']}
        noValidate
      >
        
            <div key="applicant-full-name" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="applicant-full-name" 
                  className={styles['form-label']}
                >
                  Full Name
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <input
          type="text"
          
    id="applicant-full-name"
    name="applicant-full-name"
    required
    
    placeholder="Enter your full name"
    
  
          value={formData['applicant_full_name'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${errors['applicant-full-name'] ? styles['form-input-error'] : ''}`}
        />
              
              {errors['applicant-full-name'] && (
                <p className={styles['form-error']}>{errors['applicant-full-name']}</p>
              )}
            </div>
          

            <div key="applicant-email" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="applicant-email" 
                  className={styles['form-label']}
                >
                  Email Address
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <input
          type="email"
          
    id="applicant-email"
    name="applicant-email"
    required
    
    placeholder="Enter your email address"
    
  
          value={formData['applicant_email'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${errors['applicant-email'] ? styles['form-input-error'] : ''}`}
        />
              
              {errors['applicant-email'] && (
                <p className={styles['form-error']}>{errors['applicant-email']}</p>
              )}
            </div>
          

            <div key="passport-number" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="passport-number" 
                  className={styles['form-label']}
                >
                  Passport Number
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <input
          type="text"
          
    id="passport-number"
    name="passport-number"
    required
    
    placeholder="Enter your passport number"
    
  
          value={formData['passport_number'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${errors['passport-number'] ? styles['form-input-error'] : ''}`}
        />
              
              {errors['passport-number'] && (
                <p className={styles['form-error']}>{errors['passport-number']}</p>
              )}
            </div>
          

            <div key="date-of-birth" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="date-of-birth" 
                  className={styles['form-label']}
                >
                  Date of Birth
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <input
          type="date"
          
    id="date-of-birth"
    name="date-of-birth"
    required
    
    placeholder="Enter Date of Birth"
    
  
          value={formData['date_of_birth'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${
            errors['date-of-birth'] ? styles['form-input-error'] : ''
          }`}
        />
              
              {errors['date-of-birth'] && (
                <p className={styles['form-error']}>{errors['date-of-birth']}</p>
              )}
            </div>
          

            <div key="nationality" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="nationality" 
                  className={styles['form-label']}
                >
                  Nationality
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <input
          type="text"
          
    id="nationality"
    name="nationality"
    required
    
    placeholder="Enter your nationality"
    
  
          value={formData['nationality'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${errors['nationality'] ? styles['form-input-error'] : ''}`}
        />
              
              {errors['nationality'] && (
                <p className={styles['form-error']}>{errors['nationality']}</p>
              )}
            </div>
          

            <div key="travel-dates" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="travel-dates" 
                  className={styles['form-label']}
                >
                  Expected Travel Dates
                  
                </label>
              
              
        <input
          type="date"
          
    id="travel-dates"
    name="travel-dates"
    
    
    placeholder="Enter Expected Travel Dates"
    
  
          value={formData['travel_dates'] || ''}
          onChange={handleChange}
          className={`${styles['form-input']} ${
            errors['travel-dates'] ? styles['form-input-error'] : ''
          }`}
        />
              
              {errors['travel-dates'] && (
                <p className={styles['form-error']}>{errors['travel-dates']}</p>
              )}
            </div>
          

            <div key="visa-type" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="visa-type" 
                  className={styles['form-label']}
                >
                  Type of Visa
                  <span className={styles["required-mark"]}>*</span>
                </label>
              
              
        <div className={styles['select-wrapper']}>
          <select
            id="visa-type"
            name="visa-type"
            value={formData['visa_type'] || ''}
            onChange={handleChange}
            required
            className={`${styles['form-select']} ${
              errors['visa-type'] ? styles['form-select-error'] : ''
            }`}
          >
            <option value="" disabled selected>
                Select visa type
              </option>
            <option value="Tourist">Tourist</option>
            <option value="Business">Business</option>
            <option value="Student">Student</option>
            <option value="Work">Work</option>
          </select>
          <div className={styles['select-arrow']}></div>
        </div>
              
              {errors['visa-type'] && (
                <p className={styles['form-error']}>{errors['visa-type']}</p>
              )}
            </div>
          

            <div key="additional-documents" className={styles['form-field-wrapper']}>
              
                <label 
                  htmlFor="additional-documents" 
                  className={styles['form-label']}
                >
                  Upload Additional Documents
                  
                </label>
              
              
        <div className={styles['file-input-wrapper']}>
          <input
            type="file"
            
    id="additional-documents"
    name="additional-documents"
    
    
    placeholder="Enter Upload Additional Documents"
    
  
            accept=""
            
            onChange={handleFileChange}
            className={`${styles['form-file']} ${
              errors['additional-documents'] ? styles['form-file-error'] : ''
            }`}
          />
          
        </div>
              
              {errors['additional-documents'] && (
                <p className={styles['form-error']}>{errors['additional-documents']}</p>
              )}
            </div>
          
        
        <div className={styles['form-actions']}>
          <div className={styles['button-status-wrapper']}>
            <button
              type="submit"
              className={`${styles['form-button']} ${isSubmitting ? styles['button-loading'] : ''}`}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className={styles['loading-spinner']}></span>
                  Submitting...
                </>
              ) : (
                'Submit'
              )}
            </button>
            
            {status.message && (
              <div className={`${styles['status-message']} ${styles[`status-${status.type}`]}`}>
                <span className={styles['status-icon']}>
                  {status.type === 'success' && '✓'}
                  {status.type === 'error' && '⚠'}
                </span>
                {status.message}
              </div>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}