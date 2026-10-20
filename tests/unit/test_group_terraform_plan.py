import unittest

from scripts.group_terraform_plan import group_plan


def plan_for(*addresses):
    return '\n'.join(f'  # {address} will be created' for address in addresses)


class GroupTerraformPlanTests(unittest.TestCase):
    def test_gcp_nested_network_resources_are_all_visible(self):
        self.assertEqual(
            group_plan(plan_for(
                'module.network.google_compute_router_nat.lab[0]',
                'module.network.google_compute_router.lab[0]',
                'module.network.google_compute_subnetwork.lab',
                'module.network.google_compute_network.lab',
            )),
            '1. module.network.google_compute_network.lab\n'
            '    1.1 module.network.google_compute_router.lab[0]\n'
            '        1.1.1 module.network.google_compute_router_nat.lab[0]\n'
            '    1.2 module.network.google_compute_subnetwork.lab',
        )

    def test_mixed_providers_and_indexed_modules(self):
        self.assertEqual(
            group_plan(plan_for(
                'aws_s3_bucket.docs',
                'aws_s3_bucket_policy.docs',
                'module.gke["dev"].google_container_cluster.lab',
                'module.gke["dev"].google_container_node_pool.lab',
            )),
            '1. aws_s3_bucket.docs\n'
            '    1.1 aws_s3_bucket_policy.docs\n\n'
            '2. module.gke["dev"].google_container_cluster.lab\n'
            '    2.1 module.gke["dev"].google_container_node_pool.lab',
        )

    def test_unmatched_gcp_resources_remain_top_level(self):
        addresses = [
            'google_project_service.required["compute.googleapis.com"]',
            'module.gke.google_container_cluster.lab',
            'module.gke.google_container_node_pool.cpu',
            'module.other.google_container_node_pool.lab',
            'google_compute_router.lab[0]',
            'google_compute_router_nat.lab[1]',
        ]
        result = group_plan(plan_for(*addresses))
        self.assertEqual(len(result.split('\n\n')), len(addresses))
        for address in addresses:
            self.assertIn(address, result)


if __name__ == '__main__':
    unittest.main()
