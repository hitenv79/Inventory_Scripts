#!/usr/local/bin/python3

import boto3
import Inventory_Modules
import argparse
from colorama import init, Fore, Style
from botocore.exceptions import ClientError

import logging

init()

UsageMsg="This script will correlate the Service Catalog products with the CFN Stacksets and display the account numbers associated with the SC Products. It will also make recommendations on which SC Products are ok to remove to make Landing Zone troubleshooting simpler and clearer."
parser = argparse.ArgumentParser(
	description="We\'re going to find all resources within any of the profiles we have access to.",
	prefix_chars='-+/')
parser.add_argument(
	"-p", "--profile",
	dest="pProfile",
	metavar="profile to use",
	default="default",
	help="To specify a specific profile, use this parameter. Default will be your default profile.")
parser.add_argument(
	"-r", "--region",
	dest="pregion",
	metavar="region name string",
	default="us-east-1",
	help="String fragment of the region(s) you want to check for resources.")
parser.add_argument(
	"+d", "+delete",
	dest="DeletionRun",
	metavar="Deletion of inactive Service Catalog provisioned products",
	const=True,
	default=False,
	action="store_const",
	help="This will delete the SC Provisioned Products found to be in error, or without active CloudFormation stacks - without any opportunity to confirm. Be careful!!")
parser.add_argument(
	'-v',
	help="Be verbose",
	action="store_const",
	dest="loglevel",
	const=logging.ERROR, # args.loglevel = 40
	default=logging.CRITICAL) # args.loglevel = 50
parser.add_argument(
	'-vv', '--verbose',
	help="Be MORE verbose",
	action="store_const",
	dest="loglevel",
	const=logging.WARNING, # args.loglevel = 30
	default=logging.CRITICAL) # args.loglevel = 50
parser.add_argument(
	'-d',
	help="Print debugging statements",
	action="store_const",
	dest="loglevel",
	const=logging.INFO,	# args.loglevel = 20
	default=logging.CRITICAL) # args.loglevel = 50
parser.add_argument(
	'-dd', '--debug',
	help="Print LOTS of debugging statements",
	action="store_const",
	dest="loglevel",
	const=logging.DEBUG,	# args.loglevel = 10
	default=logging.CRITICAL) # args.loglevel = 50
args = parser.parse_args()

pProfile=args.pProfile
pRegion=args.pregion
verbose=args.loglevel
DeletionRun=args.DeletionRun
logging.basicConfig(level=args.loglevel, format="[%(filename)s:%(lineno)s:%(levelname)s - %(funcName)20s() ] %(message)s")


##########################
def sort_by_email(elem):
	return(elem('AccountEmail'))
##########################
ERASE_LINE = '\x1b[2K'

print()

SCP2Stacks=[]
SCProducts=[]
ErroredSCPExists=False
session_cfn=boto3.Session(profile_name=pProfile, region_name=pRegion)
client_cfn=session_cfn.client('cloudformation')
try:
	SCresponse=Inventory_Modules.find_sc_products(pProfile, pRegion, "All")
	logging.warning("A list of the SC Products found:")
	for i in range(len(SCresponse)):
		logging.warning("SC Product Name %s | SC Product Status %s", SCresponse[i]['Name'], SCresponse[i]['Status'])
		SCProducts.append({
			'SCPName': SCresponse[i]['Name'],
			'SCPId': SCresponse[i]['Id'],
			'SCPStatus': SCresponse[i]['Status']
		})
		if SCresponse[i]['Status'] == 'ERROR' or SCresponse[i]['Status'] == 'TAINTED':
			ErroredSCPExists=True
	for i in range(len(SCProducts)):
		print(ERASE_LINE, Fore.RED+"Checking {} of {} products".format(i+1, len(SCProducts))+Fore.RESET, end='\r')
		CFNresponse=Inventory_Modules.find_stacks(pProfile, pRegion, SCProducts[i]['SCPId'])
		logging.error("There are %s matches for SC Provisioned Product Name %s", len(CFNresponse), SCProducts[i]['SCPName'])
		try:
			if len(CFNresponse) > 0:
				stack_info=client_cfn.describe_stacks(
					StackName=CFNresponse[0]['StackName']
				)
				# The above command fails if the stack found (by the find_stacks function has been deleted)
				# The following section determines the NEW Account's AccountEmail and AccountID
				if 'Parameters' in stack_info['Stacks'][0].keys() and len(stack_info['Stacks'][0]['Parameters']) > 0:
					AccountEmail='None'
					for y in range(len(stack_info['Stacks'][0]['Parameters'])):
						if stack_info['Stacks'][0]['Parameters'][y]['ParameterKey']=='AccountEmail':
							AccountEmail=stack_info['Stacks'][0]['Parameters'][y]['ParameterValue']
				if 'Outputs' in stack_info['Stacks'][0].keys():
					for y in range(len(stack_info['Stacks'][0]['Outputs'])):
						logging.error("Output Key %s for stack %s is %s", stack_info['Stacks'][0]['Outputs'][y]['OutputKey'], CFNresponse[0]['StackName'], stack_info['Stacks'][0]['Outputs'][y]['OutputValue'])
						if stack_info['Stacks'][0]['Outputs'][y]['OutputKey']=='AccountID':
							AccountID=stack_info['Stacks'][0]['Outputs'][y]['OutputValue']
							logging.error(Fore.RED+"Found the Account ID"+Fore.RESET)
							break
						else:
							logging.info("Outputs key present, but no account ID")
				else:
					logging.info("No Outputs key present")
					AccountID='None'
					AccountEmail='None'
				SCProductName=SCProducts[i]['SCPName']
				SCProductId=SCProducts[i]['SCPId']
				SCStatus=SCProducts[i]['SCPStatus']
				CFNStackName=CFNresponse[0]['StackName']
				CFNStackStatus=CFNresponse[0]['StackStatus']
			else:	# This takes effect when CFNResponse can't find any stacks with the Service Catalog Product ID
				SCProductName=SCProducts[i]['SCPName']
				SCProductId=SCProducts[i]['SCPId']
				SCStatus=SCProducts[i]['SCPStatus']
				CFNStackName='None'
				CFNStackStatus='None'
				AccountID='None'
				AccountEmail='None'
			SCP2Stacks.append({
				'SCProductName': SCProductName,
				'SCProductId': SCProductId,
				'SCStatus': SCStatus,
				'CFNStackName': CFNStackName,
				'CFNStackStatus': CFNStackStatus,
				'AccountEmail': AccountEmail,
				'AccountID': AccountID
			})
		except ClientError as my_Error:
			if str(my_Error).find("ValidationError") > 0:
				print("Validation Failure ")
				print("Validation Failure in profile {} looking for stack {} with status of {}".format(pProfile, CFNresponse[0]['StackName'], CFNresponse[0]['StackStatus']))
			elif str(my_Error).find("AccessDenied") > 0:
				print(pProfile+": Access Denied Failure ")
			else:
				print(pProfile+": Other kind of failure ")
				print(my_Error)
	# sorted_list=sorted(SCP2Stacks, key=sort_by_email)
	# SCP2Stacks=sorted_list
	fmt='%-15s %-52s %-35s %-10s %-18s %-20s'
	print()
	print(fmt % ("Account Number", "SC Product Name", "CFN Stack Name", "SC Status", "CFN Stack Status", "AccountEmail"))
	print(fmt % ("--------------", "---------------", "--------------", "---------", "----------------", "------------"))
	for i in range(len(SCP2Stacks)):
		if SCP2Stacks[i]['SCStatus']=='ERROR' or SCP2Stacks[i]['SCStatus']=='TAINTED':
			print(Fore.RED + fmt % (SCP2Stacks[i]['AccountID'], SCP2Stacks[i]['SCProductName'], SCP2Stacks[i]['CFNStackName'], SCP2Stacks[i]['SCStatus'], SCP2Stacks[i]['CFNStackStatus'],  SCP2Stacks[i]['AccountEmail'])+Style.RESET_ALL)
		else:
			print(fmt % (SCP2Stacks[i]['AccountID'], SCP2Stacks[i]['SCProductName'], SCP2Stacks[i]['CFNStackName'], SCP2Stacks[i]['SCStatus'], SCP2Stacks[i]['CFNStackStatus'],  SCP2Stacks[i]['AccountEmail']))
except ClientError as my_Error:
	if str(my_Error).find("AuthFailure") > 0:
		print(pProfile+": Authorization Failure ")
	elif str(my_Error).find("AccessDenied") > 0:
		print(pProfile+": Access Denied Failure ")
	else:
		print(pProfile+": Other kind of failure ")
		print(my_Error)

if ErroredSCPExists:
	print("You probably want to remove the following SC Products:")
	session_sc=boto3.Session(profile_name=pProfile, region_name=pRegion)
	client_sc=session_sc.client('servicecatalog')
	for i in range(len(SCP2Stacks)):
		if (SCP2Stacks[i]['SCStatus']=='ERROR') or (SCP2Stacks[i]['CFNStackName']=='None') and not DeletionRun:
			print("aws servicecatalog terminate-provisioned-product --provisioned-product-id {} --profile {} --ignore-errors".format(SCP2Stacks[i]['SCProductId'], pProfile))
		elif (SCP2Stacks[i]['SCStatus']=='ERROR') or (SCP2Stacks[i]['CFNStackName']=='None') and DeletionRun:
			print("Deleting Service Catalog Provisioned Product {} from {} profile".format(SCP2Stacks[i]['SCProductName'], pProfile))
			StackDelete=client_sc.terminate_provisioned_product(
				ProvisionedProductId=SCP2Stacks[i]['SCProductId'],
				IgnoreErrors=True,
			)
			logging.error("Result of Deletion: %s", StackDelete['RecordDetail']['Status'])
			if len(StackDelete['RecordDetail']['RecordErrors']) > 0:
				logging.error("Error code: %s", StackDelete['RecordDetail']['RecordErrors'][0]['Code'])
				logging.error("Error description: %s", StackDelete['RecordDetail']['RecordErrors'][0]['Description'])

print()
print("Thanks for using this script...")
