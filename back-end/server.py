from flask import Flask, request, jsonify
from flask_restful import Api, Resource, reqparse, fields, marshal_with
from flask_cors import CORS
from openai import OpenAI
from waitress import serve                                              
import os

key = os.getenv("OPENAI_API_KEY")
if not key:
    raise ValueError("OpenAI API key is missing")

client = OpenAI(
    api_key = key  # This is the default and can be omitted
)

app = Flask(__name__)                                                       #Initialize the flask application for the API
api = Api(app)
CORS(app)

'''Define request parser values and their properties for ADD, PUT, POST, DELETE requests'''
parsing_items = [
    "employmentIncome", 
    "pensionIncome", 
    "businessProfits", 
    "rentalIncome", 
    "educationExpenses", 
    "businessExpenses", 
    "taxWithheld"
]

rqp = reqparse.RequestParser()   
rqp.add_argument("filingStatus", type=str, choices=["single", "marriedJoint", "marriedSeparate"], required=True, help="Filing status is required")
for item in parsing_items:                                       
    rqp.add_argument(item, type=float, default=0.0) 
rqp.add_argument("dependents", type=int, default=0)

advrqp = reqparse.RequestParser()               
advrqp.add_argument("userComments", type=str, default="")                           
advrqp.add_argument("filingStatus", type=str, choices=["single", "marriedJoint", "marriedSeparate"], required=True, help="Filing status is required")
for item in parsing_items:                                      
    advrqp.add_argument(item, type=float, default=0.0) 
advrqp.add_argument("dependents", type=int, default=0)

# Define the structure of the response using fields
tax_fields = {
    "totalIncome": fields.Float,
    "deductions": fields.Float,
    "taxableIncome": fields.Float,
    "grossTax": fields.Float,
    "taxWithheld": fields.Float,
    "taxCredit": fields.Float,
    "netTaxDue": fields.Float,
}

class TaxCalculator(Resource):

    @marshal_with(tax_fields)
    def cal_tax(self):
        try:
            args = rqp.parse_args()

            # Extract input data
            # Income data
            filing_status = args.get('filingStatus')
            employment_income = args.get('employmentIncome')
            pension_income = args.get('pensionIncome')
            business_profits = args.get('businessProfits')
            rental_income = args.get('rentalIncome')
            # Expenses data
            education_expenses = args.get('educationExpenses')
            business_expenses = args.get('businessExpenses')
            # Tax withheld data
            tax_withheld = args.get('taxWithheld')
            # Dependents data
            dependents = args.get('dependents')

            # Calculate total income
            total_income = (
                employment_income +
                pension_income +
                business_profits +
                rental_income 
            )

            # Deductible expenses
            deductions = (
                education_expenses + 
                business_expenses
            )
            taxable_income = max(0, total_income - deductions)

            # Calculate income tax
            if taxable_income <= 10000:
                gross_tax = taxable_income * 0.09
            elif taxable_income <= 20000:
                gross_tax = 10000 * 0.09 + (taxable_income - 10000) * 0.22
            elif taxable_income <= 30000:
                gross_tax = 10000 * 0.09 + 10000 * 0.22 + (taxable_income - 20000) * 0.28
            else:
                gross_tax = 10000 * 0.09 + 10000 * 0.22 + 10000 * 0.28 + (taxable_income - 30000) * 0.36

            # Apply tax credits
            if filing_status != "single" or dependents > 0:
                tax_credit = 777        # Initial tax credits
                credit_scales = [33, 123, 243, 563]
                extra = 220
                if dependents > 0 and dependents < 5:
                    tax_credit += credit_scales[dependents-1]
                elif dependents >= 5:
                    tax_credit += credit_scales[-1] + extra * (dependents - len(credit_scales))

            # Calculate net tax due
            net_tax_due = max(0, gross_tax - tax_withheld - tax_credit)
            
            # Response
            response = {
                "totalIncome": total_income,
                "deductions": deductions,
                "taxableIncome": taxable_income,
                "grossTax": gross_tax,
                "taxWithheld": tax_withheld,
                "taxCredit": tax_credit,
                "netTaxDue": net_tax_due
            }

            return response, 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def dispatch_request(self, *args, **kwargs):
        # Override dispatch_request to route to the appropriate method
        if request.method == 'POST':
            return self.cal_tax()                                    # Call custom method for DELETE requests
        else:
            return super(TaxCalculator, self).dispatch_request(*args, **kwargs)

class openAIAdvisor(Resource):

    def advgenerator(self):
        try:
            
            # Extract input data and comments
            tax_data = {k: v for k, v in advrqp.parse_args().items()}
            user_comments = tax_data.pop('userComments')
            # Format input for OpenAI
            prompt = generate_prompt(tax_data, user_comments)
            # Query OpenAI API
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a tax advisor. Provide practical suggestions."},     # The role gpt will play (tax advisor)
                    {"role": "user", "content": prompt}     # The user's input
                ],
                temperature=0.7,
                max_tokens=750
            )
            # Extract and return OpenAI response
            advice = response.choices[0].message.content   # Navigate through gpt's json response and get the content we need
            
            return {'advice': advice}, 200

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    def dispatch_request(self, *args, **kwargs):
        # Override dispatch_request to route to the appropriate method
        if request.method == 'POST':
            return self.advgenerator()                                    # Call custom method for DELETE requests
        else:
            return super(openAIAdvisor, self).dispatch_request(*args, **kwargs)

api.add_resource(TaxCalculator, "/calculate-tax",
                methods=['POST']) 

api.add_resource(openAIAdvisor, "/tax-advice",
                methods=['POST']) 

def generate_prompt(tax_data, comments):
    """
    Formats the user input into a cohesive prompt for OpenAI.
    """
    tax_data_str = "\n".join([f"{k}: {v}" for k, v in tax_data.items()])
    if comments:
        return (
            f"Here is the user's tax-related data:\n{tax_data_str}\n\n"
            f"The user has also shared the following comments:\n{comments}\n\n"
            "Based on this information, please provide personalized suggestions and advice regarding their taxes."
        )
    return (
        f"Here is the user's tax-related data:\n{tax_data_str}\n\n"
        "Based on this information, please provide personalized suggestions and advice regarding their taxes."
    ) 

if __name__ == "__main__":

    print("Server starting up!")
    print(f"Ip: {'0.0.0.0'}, Port: 5000")
    serve(app, port=5000)    