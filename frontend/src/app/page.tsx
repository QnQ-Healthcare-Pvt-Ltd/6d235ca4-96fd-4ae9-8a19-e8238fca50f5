
'use client';

import { useState } from 'react';
import VisaApplicationFormComponent from '../components/forms/VisaApplicationFormComponent';

export default function FormPage() {
  const [status, setStatus] = useState({ type: '', message: '' });

  const handleSubmit = async (data: any) => {
    console.log(data);
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Visa Application Form</h1>
      {status.message && (
        <div className={`p-4 mb-4 rounded ${status.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {status.message}
        </div>
      )}
      <VisaApplicationFormComponent onSubmit={handleSubmit} />
    </div>
  );
}