"""Group a Terraform text plan using resource types and matching local names.

This is a presentation convention, not dependency analysis. Text plans do not
preserve the configuration references needed to infer ownership reliably.
Unknown types and ambiguous matches remain top-level resources.
"""

import argparse
import re
from pathlib import Path


PARENT_TYPES = {
    # API components share a REST API parent; account settings remain top-level.
    'aws_api_gateway_resource': 'aws_api_gateway_rest_api',
    'aws_api_gateway_method': 'aws_api_gateway_rest_api',
    'aws_api_gateway_integration': 'aws_api_gateway_rest_api',
    'aws_api_gateway_deployment': 'aws_api_gateway_rest_api',
    'aws_api_gateway_stage': 'aws_api_gateway_rest_api',
    'aws_api_gateway_method_settings': 'aws_api_gateway_rest_api',
    'aws_api_gateway_rest_api_policy': 'aws_api_gateway_rest_api',
    'aws_s3_bucket_public_access_block': 'aws_s3_bucket',
    'aws_s3_bucket_ownership_controls': 'aws_s3_bucket',
    'aws_s3_bucket_versioning': 'aws_s3_bucket',
    'aws_s3_bucket_server_side_encryption_configuration': 'aws_s3_bucket',
    'aws_s3_bucket_policy': 'aws_s3_bucket',
    'aws_s3vectors_index': 'aws_s3vectors_vector_bucket',
    'aws_iam_role_policy': 'aws_iam_role',
    'aws_bedrockagent_data_source': 'aws_bedrockagent_knowledge_base',
    'aws_cloudwatch_log_metric_filter': 'aws_cloudwatch_log_group',
}
ADDRESS = re.compile(
    r'^(?P<module>(?:module\.[\w-]+(?:\[(?:"(?:[^"\\]|\\.)*"|\d+)\])?\.)*)'
    r'(?P<type>aws_\w+)\.(?P<name>[\w-]+)'
    r'(?P<index>\[(?:"(?:[^"\\]|\\.)*"|\d+)\])?$'
)


def group_plan(plan):
    plan = re.sub(r'\x1b\[[0-9;]*m', '', plan)
    resources = {}
    for line in plan.splitlines():
        header = re.match(r'^\s*# (.+?) (?:will be |must be |has been )', line)
        if header:
            address = header.group(1)
            match = ADDRESS.fullmatch(address)
            if match:
                resources[address] = match.groupdict()

    children = {address: [] for address in resources}
    nested = set()
    for address, parts in resources.items():
        parent_type = PARENT_TYPES.get(parts['type'])
        candidates = [
            candidate for candidate, parent in resources.items()
            if parent['type'] == parent_type
            and parent['module'] == parts['module']
            and parent['name'] == parts['name']
            and (parent['index'] is None or parent['index'] == parts['index'])
        ]
        if len(candidates) == 1:
            children[candidates[0]].append(address)
            nested.add(address)

    groups = []
    for group_number, address in enumerate(sorted(resources.keys() - nested), start=1):
        groups.append('\n'.join(
            [f'{group_number}. {address}'] + [
                f'    {group_number}.{child_number} {child}'
                for child_number, child in enumerate(sorted(children[address]), start=1)
            ]
        ))
    return '\n\n'.join(groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path, help='Terraform text plan, e.g. tfout.txt')
    args = parser.parse_args()
    try:
        result = group_plan(args.plan.read_text())
    except OSError as error:
        parser.exit(1, f'{error}\n')
    if not result:
        parser.exit(1, 'No AWS resource action headers found in the text plan.\n')
    print(result)


if __name__ == '__main__':
    main()
